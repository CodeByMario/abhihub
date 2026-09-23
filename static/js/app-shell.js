/**
 * AbhiHub App Shell Controller (app-shell.js)
 * Manages the native-app shell container:
 * - Tab switching with keep-alive for Upload
 * - Same-origin iframe coordination & history synchronization
 * - Top-level escape for Auth / Expired Sessions
 * - Mobile keyboard & modal detection
 * - Notification bell & slow-network handling
 */
(function () {
    'use strict';

    // ── Tab Configuration ──
    const TABS = {
        '/dashboard': { id: 'home', label: 'Home', selector: '[data-page="home"]', keepAlive: false },
        '/upload': { id: 'upload', label: 'Upload', selector: '[data-page="upload"]', keepAlive: true },
        '/leaderboard': { id: 'ranking', label: 'Ranking', selector: '[data-page="ranking"]', keepAlive: false },
        '/rank': { id: 'ranking', label: 'Ranking', selector: '[data-page="ranking"]', keepAlive: false },
        '/settings': { id: 'settings', label: 'Settings', selector: '[data-page="settings"]', keepAlive: false },
        '/setting': { id: 'settings', label: 'Settings', selector: '[data-page="settings"]', keepAlive: false },
        '/profile': { id: 'settings', label: 'Settings', selector: '[data-page="settings"]', keepAlive: false },
        '/account': { id: 'settings', label: 'Account', selector: '[data-page="settings"]', keepAlive: false },
        '/store-room': { id: 'store-room', label: 'Store Room', selector: '[data-page="store-room"]', keepAlive: false },
        '/admin/controle': { id: 'admin', label: 'Admin', selector: '[data-page="admin"]', keepAlive: false }
    };

    // DOM Elements
    const mainArea = document.getElementById('shellMainArea');
    const iframeMain = document.getElementById('shellIframe');
    const iframeUpload = document.getElementById('shellIframeUpload');
    const loader = document.getElementById('shellLoader');
    const slowMsg = document.getElementById('shellSlowMsg');
    const retryBtn = document.getElementById('shellRetryBtn');
    const homeFallbackBtn = document.getElementById('shellHomeFallbackBtn');
    const headerEl = document.getElementById('shellHeader');
    const backBtn = document.getElementById('shellBackBtn');
    const pageTitle = document.getElementById('shellPageTitle');
    const bottomNav = document.getElementById('shellBottomNav');
    const notifBell = document.getElementById('shellNotifBell');
    const notifBadge = document.getElementById('shellNotifBadge');
    const notifPanel = document.getElementById('shellNotifPanel');
    const notifList = document.getElementById('shellNotifList');

    let currentActiveTab = null;
    let activeIframe = iframeMain;
    let slowTimer = null;
    const SLOW_TIMEOUT_MS = 8000;

    // ── Loader Helpers ──
    function showLoader() {
        if (!loader) return;
        loader.classList.remove('is-hidden');
        if (slowMsg) slowMsg.classList.remove('is-visible');

        clearTimeout(slowTimer);
        slowTimer = setTimeout(function () {
            if (loader && !loader.classList.contains('is-hidden') && slowMsg) {
                slowMsg.classList.add('is-visible');
            }
        }, SLOW_TIMEOUT_MS);
    }

    function hideLoader() {
        if (!loader) return;
        loader.classList.add('is-hidden');
        if (slowMsg) slowMsg.classList.remove('is-visible');
        clearTimeout(slowTimer);
    }

    if (retryBtn) {
        retryBtn.addEventListener('click', function () {
            showLoader();
            try {
                activeIframe.contentWindow.location.reload();
            } catch (e) {
                activeIframe.src = activeIframe.src;
            }
        });
    }

    if (homeFallbackBtn) {
        homeFallbackBtn.addEventListener('click', function () {
            navigateTo('/dashboard');
        });
    }

    // ── Get Tab Config for Path ──
    function getTabForPath(pathname) {
        const cleanPath = pathname.split('?')[0].split('#')[0];
        return TABS[cleanPath] || null;
    }

    // ── Update Chrome (Header & Bottom Nav) ──
    function updateChrome(path, title) {
        const tab = getTabForPath(path);

        // Highlight active tab in bottom nav
        const navItems = bottomNav ? bottomNav.querySelectorAll('.navbar__item') : [];
        navItems.forEach(item => item.classList.remove('navbar__item--active'));

        // Highlight active tab in desktop header nav
        const desktopNav = document.getElementById('shellDesktopNav');
        const desktopLinks = desktopNav ? desktopNav.querySelectorAll('.shell-nav-link') : [];
        desktopLinks.forEach(link => link.classList.remove('shell-nav-link--active'));

        if (tab) {
            currentActiveTab = tab.id;
            const activeEl = bottomNav ? bottomNav.querySelector(tab.selector) : null;
            if (activeEl) activeEl.classList.add('navbar__item--active');

            const activeDesktopEl = desktopNav ? desktopNav.querySelector(tab.selector) : null;
            if (activeDesktopEl) activeDesktopEl.classList.add('shell-nav-link--active');

            // On a main tab: hide back button, show main logo
            if (headerEl) headerEl.classList.remove('has-back-nav');
        } else {
            // On a sub-page: show back button and page title
            if (headerEl) headerEl.classList.add('has-back-nav');
            if (pageTitle && title) {
                pageTitle.textContent = title;
            }
        }
    }

    // ── Tab / URL Navigation ──
    function navigateTo(targetUrl, isTabSwitch = false) {
        const urlObj = new URL(targetUrl, window.location.origin);
        const targetPath = urlObj.pathname + urlObj.search + urlObj.hash;
        const tab = getTabForPath(urlObj.pathname);

        // Handle Keep-Alive for Upload
        if (tab && tab.id === 'upload') {
            activeIframe = iframeUpload;
            iframeMain.style.display = 'none';
            iframeUpload.style.display = 'block';

            // First time loading upload iframe?
            if (!iframeUpload.dataset.loaded) {
                showLoader();
                iframeUpload.src = targetPath;
                iframeUpload.dataset.loaded = 'true';
            } else {
                // Already loaded, instant display!
                hideLoader();
                updateChrome(targetPath, 'Upload');
                syncShellUrl(targetPath);
                return;
            }
        } else {
            // Normal tab or sub-page -> use main iframe
            activeIframe = iframeMain;
            if (iframeUpload) iframeUpload.style.display = 'none';
            iframeMain.style.display = 'block';

            showLoader();

            if (isTabSwitch) {
                try {
                    iframeMain.contentWindow.location.replace(targetPath);
                } catch (e) {
                    iframeMain.src = targetPath;
                }
            } else {
                iframeMain.src = targetPath;
            }
        }

        syncShellUrl(targetPath);
    }

    function syncShellUrl(innerPath) {
        const newShellUrl = '/app-shell?p=' + encodeURIComponent(innerPath);
        if (window.location.search !== '?p=' + encodeURIComponent(innerPath)) {
            history.pushState({ path: innerPath }, '', newShellUrl);
        }
    }

    // ── Safe Auth Escape & Iframe Destruction ──
    function destroyIframesAndEscape(redirectUrl) {
        try { iframeMain.src = 'about:blank'; } catch (e) {}
        try { if (iframeUpload) iframeUpload.src = 'about:blank'; } catch (e) {}
        window.location.href = redirectUrl;
    }

    // ── Handle Iframe Load ──
    function onIframeLoaded(iframeEl) {
        if (iframeEl !== activeIframe) return;

        hideLoader();
        // Reset modal state on every iframe load
        document.body.classList.remove('modal-active');

        try {
            const innerWin = iframeEl.contentWindow;
            const innerDoc = iframeEl.contentDocument || innerWin.document;
            const innerPath = innerWin.location.pathname + innerWin.location.search + innerWin.location.hash;

            // Security & Auth escape check
            if (/^\/(login|signup|logout|auth(\/|$))/i.test(innerWin.location.pathname)) {
                destroyIframesAndEscape('/login?next=' + encodeURIComponent(innerPath));
                return;
            }

            const pageDocTitle = innerDoc ? innerDoc.title : 'AbhiHub';
            updateChrome(innerPath, pageDocTitle);
            document.title = pageDocTitle ? pageDocTitle + ' — AbhiHub' : 'AbhiHub';

            // Replace state in shell history
            const cleanShellUrl = '/app-shell?p=' + encodeURIComponent(innerPath);
            history.replaceState({ path: innerPath }, '', cleanShellUrl);
        } catch (e) {
            console.warn('[AppShell] Cross-origin or restricted iframe access:', e);
        }
    }

    iframeMain.addEventListener('load', function () {
        onIframeLoaded(iframeMain);
    });

    if (iframeUpload) {
        iframeUpload.addEventListener('load', function () {
            iframeUpload.dataset.loaded = 'true';
            onIframeLoaded(iframeUpload);
        });
    }

    // ── Bottom Nav Click Delegation ──
    if (bottomNav) {
        bottomNav.addEventListener('click', function (e) {
            const anchor = e.target.closest('.navbar__item');
            if (!anchor) return;

            e.preventDefault();
            const href = anchor.getAttribute('href');
            if (!href) return;

            const targetTab = getTabForPath(href);

            // If tapping already-active tab, scroll to top
            if (targetTab && targetTab.id === currentActiveTab) {
                try {
                    activeIframe.contentWindow.postMessage({ type: 'SCROLL_TOP' }, window.location.origin);
                } catch (err) {}
                return;
            }

            navigateTo(href, true);
        });
    }

    // ── Desktop Header Navigation Click Handler ──
    const desktopNav = document.getElementById('shellDesktopNav');
    if (desktopNav) {
        desktopNav.addEventListener('click', function (e) {
            const anchor = e.target.closest('a');
            if (!anchor) return;
            const href = anchor.getAttribute('href');
            if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
            e.preventDefault();
            navigateTo(href, true);
        });
    }

    // ── Header Theme Toggle Button Handler ──
    const themeToggleBtn = document.getElementById('shellThemeToggle');
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', function () {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
            try {
                localStorage.setItem('abhihub_theme', nextTheme);
            } catch (e) {}
            applyShellTheme(nextTheme);
        });
    }

    // ── Back Button Handler ──
    if (backBtn) {
        backBtn.addEventListener('click', function () {
            try {
                if (activeIframe.contentWindow.history.length > 1) {
                    activeIframe.contentWindow.history.back();
                } else {
                    navigateTo('/dashboard', true);
                }
            } catch (e) {
                navigateTo('/dashboard', true);
            }
        });
    }

    // ── Handle Browser Back / Forward & Android Back Gesture ──
    window.addEventListener('popstate', function (event) {
        if (event.state && event.state.path) {
            navigateTo(event.state.path, true);
        } else {
            const urlParams = new URLSearchParams(window.location.search);
            const p = urlParams.get('p') || '/dashboard';
            navigateTo(p, true);
        }
    });

    // ── Bridge Messages from Inner Iframe ──
    window.addEventListener('message', function (event) {
        if (event.origin !== window.location.origin) return;
        const msg = event.data;
        if (!msg || typeof msg !== 'object') return;

        switch (msg.type) {
            case 'AUTH_EXPIRED':
                destroyIframesAndEscape('/login?next=' + encodeURIComponent(msg.url || '/dashboard'));
                break;

            case 'MODAL_OPEN':
                document.body.classList.add('modal-active');
                break;

            case 'MODAL_CLOSE':
                document.body.classList.remove('modal-active');
                break;

            case 'THEME_CHANGE':
                applyShellTheme(msg.theme);
                break;

            case 'PAGE_READY':
                hideLoader();
                if (msg.title) {
                    updateChrome(msg.path || '', msg.title);
                }
                applyShellTheme();
                break;

            case 'TITLE_CHANGE':
                if (msg.title) {
                    if (pageTitle && headerEl.classList.contains('has-back-nav')) {
                        pageTitle.textContent = msg.title;
                    }
                    document.title = msg.title + ' — AbhiHub';
                }
                break;

            case 'TARIKA_TOGGLE':
                if (typeof window.toggleAbhiAiDrawer === 'function') {
                    window.toggleAbhiAiDrawer();
                }
                break;

            case 'TARIKA_ASK':
                if (typeof window.askAiAboutFile === 'function') {
                    window.askAiAboutFile(msg.prompt || '');
                }
                break;

            case 'TARIKA_SET_DOC':
                if (typeof window.setTarikaDocContext === 'function') {
                    window.setTarikaDocContext(msg.docId, msg.docTitle);
                }
                break;
        }
    });

    // Expose navigateTo globally so persistent Tarika assistant can navigate active iframe
    window.navigateTo = navigateTo;

    // ── Mobile Keyboard Viewport Resize Handler ──
    if (window.visualViewport) {
        const initialHeight = window.visualViewport.height;
        window.visualViewport.addEventListener('resize', function () {
            // If viewport shrunk by > 150px, virtual keyboard is open
            const isKeyboardOpen = (initialHeight - window.visualViewport.height) > 150;
            if (isKeyboardOpen) {
                document.body.classList.add('keyboard-active');
            } else {
                document.body.classList.remove('keyboard-active');
            }
        });
    }

    // ── Notification Bell in Shell ──
    let notifOpen = false;
    let lastUnreadCount = 0;

    function timeAgo(iso) {
        const diff = Date.now() - new Date(iso).getTime();
        const m = Math.floor(diff / 60000);
        if (m < 1) return 'just now';
        if (m < 60) return m + 'm ago';
        const h = Math.floor(m / 60);
        if (h < 24) return h + 'h ago';
        return Math.floor(h / 24) + 'd ago';
    }

    function renderNotifications(items) {
        if (!notifList) return;
        if (!items || !items.length) {
            notifList.innerHTML = '<div class="notif-loading" style="padding:16px;text-align:center;color:#64748b;">No notifications yet 🎉</div>';
            return;
        }

        notifList.innerHTML = items.map(n => `
            <div class="notif-item ${n.is_read ? '' : 'unread'}" data-notif-id="${n.id}" data-link="${n.target_url || '/notifications'}" style="padding:10px 14px;border-bottom:1px solid #f1f5f9;cursor:pointer;display:flex;gap:10px;">
                <div style="font-size:1.2rem;">${n.type === 'file_view' ? '👁' : '🔔'}</div>
                <div style="flex:1;min-width:0;">
                    <div style="font-weight:600;font-size:0.875rem;color:#1e293b;">${n.title}</div>
                    <div style="font-size:0.8rem;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${n.message}</div>
                    <div style="font-size:0.75rem;color:#94a3b8;margin-top:2px;">${timeAgo(n.created_at)}</div>
                </div>
                ${!n.is_read ? '<div style="width:8px;height:8px;border-radius:50%;background:#2563eb;align-self:center;"></div>' : ''}
            </div>
        `).join('');
    }

    let pollIntervalMs = 60 * 1000;
    const MIN_POLL_MS = 60 * 1000;
    const MAX_POLL_MS = 10 * 60 * 1000;
    let pollTimer = null;

    function scheduleNextPoll() {
        clearTimeout(pollTimer);
        if (!document.hidden) {
            pollTimer = setTimeout(() => fetchNotifications(true), pollIntervalMs);
        }
    }

    async function fetchNotifications(silent = true) {
        if (document.hidden) return;
        try {
            const resp = await fetch('/api/my-notifications?limit=20', { signal: AbortSignal.timeout(8000) });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            if (data.success) {
                pollIntervalMs = MIN_POLL_MS; // reset on success
                lastUnreadCount = data.unread || 0;
                if (notifBadge) {
                    if (lastUnreadCount > 0) {
                        notifBadge.style.display = 'block';
                        notifBadge.textContent = lastUnreadCount > 9 ? '9+' : lastUnreadCount;
                    } else {
                        notifBadge.style.display = 'none';
                    }
                }
                if (notifOpen || !silent) {
                    renderNotifications(data.data || []);
                }
            }
        } catch (e) {
            // Exponential backoff on failure
            pollIntervalMs = Math.min(pollIntervalMs * 2, MAX_POLL_MS);
        } finally {
            scheduleNextPoll();
        }
    }

    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) {
            fetchNotifications(true);
        } else {
            clearTimeout(pollTimer);
        }
    });

    if (notifBell) {
        notifBell.addEventListener('click', function () {
            notifOpen = !notifOpen;
            if (notifPanel) notifPanel.style.display = notifOpen ? 'block' : 'none';
            if (notifOpen) {
                fetchNotifications(false);
            }
        });
    }

    // Click inside notification panel -> load destination inside active iframe!
    if (notifPanel) {
        notifPanel.addEventListener('click', function (e) {
            const item = e.target.closest('.notif-item');
            if (item) {
                const targetUrl = item.getAttribute('data-link');
                const notifId = item.getAttribute('data-notif-id');
                if (notifId) {
                    fetch('/api/notifications/' + notifId + '/read', { method: 'POST' }).catch(() => {});
                }
                notifOpen = false;
                notifPanel.style.display = 'none';
                if (targetUrl) {
                    navigateTo(targetUrl);
                }
                return;
            }

            const markAllBtn = e.target.closest('[data-action="markAllRead"]');
            if (markAllBtn) {
                fetch('/api/my-notifications/read', { method: 'POST' })
                    .then(() => {
                        if (notifBadge) notifBadge.style.display = 'none';
                        fetchNotifications(false);
                    })
                    .catch(() => {});
            }
        });
    }

    // Close panel on outside click
    document.addEventListener('click', function (e) {
        const wrap = document.getElementById('shellNotifWrap');
        if (wrap && !wrap.contains(e.target) && notifOpen) {
            notifOpen = false;
            if (notifPanel) notifPanel.style.display = 'none';
        }
    });

    // ── Theme Synchronization ──
    function applyShellTheme(themeValue) {
        try {
            const theme = themeValue || localStorage.getItem('abhihub_theme') || 'system';
            const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
            document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');

            // Update Header Theme Toggle Icons
            const sunIcon = document.querySelector('.theme-icon-sun');
            const moonIcon = document.querySelector('.theme-icon-moon');
            if (sunIcon && moonIcon) {
                if (isDark) {
                    sunIcon.style.display = 'none';
                    moonIcon.style.display = 'block';
                } else {
                    sunIcon.style.display = 'block';
                    moonIcon.style.display = 'none';
                }
            }

            [iframeMain, iframeUpload].forEach(function (iframe) {
                try {
                    if (iframe && iframe.contentDocument && iframe.contentDocument.documentElement) {
                        iframe.contentDocument.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
                    }
                } catch (e) {}
            });
        } catch (e) {}
    }

    applyShellTheme();

    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
            applyShellTheme();
        });
    }

    window.addEventListener('storage', function (e) {
        if (e.key === 'abhihub_theme') {
            applyShellTheme(e.newValue);
        }
    });

    // ── Initial Boot ──
    const urlParams = new URLSearchParams(window.location.search);
    const initialPath = urlParams.get('p') || '/dashboard';
    if (iframeMain.getAttribute('src') !== initialPath) {
        iframeMain.src = initialPath;
    }

    // Highlight initial tab
    updateChrome(initialPath, 'AbhiHub');

    // Dynamically check user profile for admin tab (keeps shell HTML 100% generic for precaching)
    async function checkUserInfo() {
        try {
            const resp = await fetch('/api/profile', { signal: AbortSignal.timeout(6000) });
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.success && data.user) {
                const adminTab = document.getElementById('shellAdminTab');
                const userEmail = (data.user.email || '').toLowerCase();
                if (adminTab && ['codebymario@gmail.com', 'info@abhihub.edu.eu.org', 'admin@abhihub.edu.eu.org'].includes(userEmail)) {
                    adminTab.style.display = 'flex';
                }
            }
        } catch (e) {
            // non-fatal
        }
    }
    checkUserInfo();

    // Initial notification check (subsequent polls scheduled dynamically with backoff)
    fetchNotifications(true);
})();
