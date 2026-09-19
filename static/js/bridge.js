/**
 * AbhiHub App Shell Bridge (bridge.js)
 * Loaded on all pages inside p_struct.html.
 * When page is rendered inside the App Shell iframe:
 * - Detects embedded mode
 * - Communicates with the outer App Shell via postMessage
 * - Intercepts 401 Unauthorized API responses -> triggers shell AUTH_EXPIRED
 * - Routes auth (login/signup/logout) & payment & external links to top-level window
 * - Notifies shell on modal open/close to hide/show shell bottom navigation
 * - Syncs document title and route state
 * When page is accessed standalone: does nothing, zero overhead.
 */
(function () {
    'use strict';

    const isEmbedded = window.name === 'abhihub-shell' && window.self !== window.top;
    if (!isEmbedded) {
        // Standalone mode - inactive
        return;
    }

    const TARGET_ORIGIN = window.location.origin;

    function postToParent(message) {
        try {
            window.parent.postMessage(message, TARGET_ORIGIN);
        } catch (e) {
            console.warn('[Bridge] Failed to post message to parent:', e);
        }
    }

    // 1. Wrap fetch to catch 401 Unauthorized (only for same-origin session expiry, clones response)
    const originalFetch = window.fetch;
    window.fetch = async function (input, init) {
        let requestUrl = '';
        if (typeof input === 'string') {
            requestUrl = input;
        } else if (input instanceof URL) {
            requestUrl = input.href;
        } else if (input && input.url) {
            requestUrl = input.url;
        }

        let isSameOrigin = true;
        try {
            const urlObj = new URL(requestUrl, window.location.origin);
            isSameOrigin = (urlObj.origin === window.location.origin);
        } catch (e) {
            isSameOrigin = false;
        }

        const response = await originalFetch.apply(this, arguments);

        // Only inspect same-origin 401 responses
        if (isSameOrigin && response && response.status === 401) {
            try {
                const reqPath = new URL(requestUrl, window.location.origin).pathname;
                // Exclude explicit credential validation endpoints (e.g. submitting login form)
                const isAuthValidationEndpoint = /^\/(api\/auth\/login|login|signup|api\/verify)/i.test(reqPath);
                if (!isAuthValidationEndpoint) {
                    // Clone response to inspect without draining caller stream
                    const cloned = response.clone();
                    cloned.json().then(data => {
                        if (!data || (data.error !== 'invalid_credentials' && data.error !== 'wrong_password')) {
                            postToParent({
                                type: 'AUTH_EXPIRED',
                                url: window.location.pathname + window.location.search
                            });
                        }
                    }).catch(() => {
                        postToParent({
                            type: 'AUTH_EXPIRED',
                            url: window.location.pathname + window.location.search
                        });
                    });
                }
            } catch (err) {
                // Non-fatal
            }
        }
        return response;
    };

    // 2. Wrap window.open to escape iframe for auth, payment, and external destinations
    const originalWindowOpen = window.open;
    window.open = function (url, target, features) {
        if (!url) return originalWindowOpen.apply(this, arguments);
        try {
            const targetUrl = new URL(url, window.location.origin);
            const isAuthRoute = /^\/(login|signup|logout|auth(\/|$)|forgot-password|reset-password|google\/callback)/i.test(targetUrl.pathname);
            const isPaymentRoute = /checkout|payment|razorpay|cashfree|stripe/i.test(targetUrl.pathname);
            const isExternal = (targetUrl.origin !== window.location.origin);

            if (isAuthRoute || isPaymentRoute || isExternal) {
                if (window.top && window.top !== window.self) {
                    return window.top.open(targetUrl.href, target || '_blank', features);
                }
            }
        } catch (e) {}
        return originalWindowOpen.apply(this, arguments);
    };

    // 3. Intercept link clicks: Auth, Payments, and External links must escape iframe
    document.addEventListener('click', function (e) {
        const anchor = e.target.closest('a');
        if (!anchor || !anchor.href) return;

        const href = anchor.getAttribute('href');
        if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;

        try {
            const targetUrl = new URL(anchor.href, window.location.origin);

            // Auth paths -> always top-level window
            const isAuthRoute = /^\/(login|signup|logout|auth(\/|$)|forgot-password|reset-password|google\/callback)/i.test(targetUrl.pathname);
            if (isAuthRoute) {
                e.preventDefault();
                window.top.location.href = targetUrl.href;
                return;
            }

            // External origin -> open in new window or top-level
            if (targetUrl.origin !== window.location.origin) {
                if (anchor.target === '_blank') {
                    return;
                }
                e.preventDefault();
                window.top.location.href = targetUrl.href;
                return;
            }

            // Payment gateways / checkout redirects
            const isPaymentRoute = /checkout|payment|razorpay|cashfree|stripe/i.test(targetUrl.pathname);
            if (isPaymentRoute) {
                e.preventDefault();
                window.top.location.href = targetUrl.href;
                return;
            }
        } catch (err) {
            // Malformed URL, ignore
        }
    }, true);

    // 3. Modal / Overlay detection -> notify Shell to toggle bottom navigation
    let modalCount = 0;

    function checkActiveModals() {
        const modalSelectors = [
            '.global-entity-modal.show',
            '.global-entity-modal[style*="display: block"]',
            '.global-entity-modal[style*="display: flex"]',
            '.popup-overlay.show',
            '.popup-overlay[style*="display: block"]',
            '.profile-nudge-overlay.show',
            '#promoCardOverlay.show',
            '.modal.show',
            '.modal[style*="display: block"]',
            '[role="dialog"].show',
            '[role="dialog"][style*="display: block"]'
        ];

        let hasOpenModal = false;
        for (let i = 0; i < modalSelectors.length; i++) {
            const el = document.querySelector(modalSelectors[i]);
            if (el && el.offsetParent !== null) {
                hasOpenModal = true;
                break;
            }
        }

        // Also check if body has modal scroll lock
        if (!hasOpenModal && document.body.style.overflow === 'hidden') {
            hasOpenModal = true;
        }

        if (hasOpenModal && modalCount === 0) {
            modalCount = 1;
            postToParent({ type: 'MODAL_OPEN' });
        } else if (!hasOpenModal && modalCount > 0) {
            modalCount = 0;
            postToParent({ type: 'MODAL_CLOSE' });
        }
    }

    // Observe DOM for modal opening/closing
    const observer = new MutationObserver(function () {
        checkActiveModals();
    });

    if (document.body) {
        observer.observe(document.body, {
            attributes: true,
            attributeFilter: ['class', 'style'],
            subtree: true,
            childList: true
        });
    } else {
        document.addEventListener('DOMContentLoaded', function () {
            observer.observe(document.body, {
                attributes: true,
                attributeFilter: ['class', 'style'],
                subtree: true,
                childList: true
            });
        });
    }

    // 4. Page Ready & Title change notification
    function notifyPageReady() {
        postToParent({
            type: 'PAGE_READY',
            path: window.location.pathname + window.location.search + window.location.hash,
            title: document.title
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', notifyPageReady);
    } else {
        notifyPageReady();
    }

    // Observe <title> changes
    const titleEl = document.querySelector('title');
    if (titleEl) {
        const titleObserver = new MutationObserver(function () {
            postToParent({
                type: 'TITLE_CHANGE',
                title: document.title
            });
        });
        titleObserver.observe(titleEl, { childList: true, characterData: true, subtree: true });
    }

    // 5. Handle messages from Shell to inner page
    window.addEventListener('message', function (event) {
        if (event.origin !== window.location.origin) return;
        const msg = event.data;
        if (!msg || typeof msg !== 'object') return;

        if (msg.type === 'SCROLL_TOP') {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        } else if (msg.type === 'RELOAD_PAGE') {
            window.location.reload();
        }
    });

    // 6. Expose global bridge helper
    window.AbhiHubBridge = {
        isEmbedded: true,
        notifyModalOpen: function () { postToParent({ type: 'MODAL_OPEN' }); },
        notifyModalClose: function () { postToParent({ type: 'MODAL_CLOSE' }); },
        notifyAuthExpired: function () {
            postToParent({
                type: 'AUTH_EXPIRED',
                url: window.location.pathname + window.location.search
            });
        }
    };
})();
