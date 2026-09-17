/**
 * AbhiHub Push Notification Client
 * Handles push notification subscription and permission management.
 * Connects to unified /sw.js service worker.
 */
(function () {
    'use strict';

    var VAPID_KEY_URL = '/api/push/vapid-public-key';
    var SUBSCRIBE_URL = '/api/push/subscribe';
    var UNSUBSCRIBE_URL = '/api/push/unsubscribe';
    var STATUS_URL = '/api/push/status';

    var _swReg = null;

    // ── Helpers ─────────────────────────────────────────────────
    function isSupported() {
        return 'Notification' in window &&
            'serviceWorker' in navigator &&
            'PushManager' in window;
    }

    function urlBase64ToUint8Array(base64String) {
        var padding = '='.repeat((4 - base64String.length % 4) % 4);
        var base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');
        var rawData = window.atob(base64);
        var outputArray = new Uint8Array(rawData.length);
        for (var i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    function getPlatformMetadata() {
        var ua = (navigator.userAgent || '').toLowerCase();
        var platform = 'unknown';
        var deviceType = 'desktop';
        var browser = 'unknown';

        if (/iphone|ipad|ipod/.test(ua)) {
            platform = 'ios';
            deviceType = /ipad/.test(ua) ? 'tablet' : 'mobile';
        } else if (/android/.test(ua)) {
            platform = 'android';
            deviceType = 'mobile';
        } else if (/macintosh|mac os x/.test(ua)) {
            platform = 'macos';
            deviceType = 'desktop';
        } else if (/windows/.test(ua)) {
            platform = 'windows';
            deviceType = 'desktop';
        } else if (/linux/.test(ua)) {
            platform = 'linux';
            deviceType = 'desktop';
        }

        if (/edg\//.test(ua)) browser = 'edge';
        else if (/chrome|crios/.test(ua)) browser = 'chrome';
        else if (/firefox|fxios/.test(ua)) browser = 'firefox';
        else if (/safari/.test(ua)) browser = 'safari';

        return { platform: platform, device_type: deviceType, browser: browser };
    }

    function trackSafeEvent(eventName, eventData) {
        try {
            if (window.AbhiHubTracking && typeof window.AbhiHubTracking.trackEvent === 'function') {
                window.AbhiHubTracking.trackEvent(eventName, eventData || {});
            }
        } catch (e) {}
    }

    function isStandalone() {
        return (window.navigator.standalone === true) || (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches);
    }

    function isIos() {
        var ua = (navigator.userAgent || '').toLowerCase();
        return /iphone|ipad|ipod/.test(ua);
    }

    // ── Service Worker registration (Unified to /sw.js) ──────────
    function registerServiceWorker() {
        if (_swReg) return Promise.resolve(_swReg);
        if (!('serviceWorker' in navigator)) return Promise.resolve(null);
        return navigator.serviceWorker.register('/sw.js', {
            scope: '/'
        }).then(function (reg) {
            _swReg = reg;
            return navigator.serviceWorker.ready.then(function (readyReg) {
                _swReg = readyReg;
                return readyReg;
            });
        }).catch(function (err) {
            console.warn('[Push] SW registration failed:', err);
            return null;
        });
    }

    // ── Get current subscription ───────────────────────────────
    function getSubscription() {
        if (!isSupported()) return Promise.resolve(null);
        return registerServiceWorker().then(function (reg) {
            if (!reg || !reg.pushManager) return null;
            return reg.pushManager.getSubscription();
        });
    }

    // ── Request notification permission ─────────────────────────
    function requestPermission() {
        if (!('Notification' in window)) return Promise.resolve('denied');
        trackSafeEvent('notification_permission_prompted');
        return Notification.requestPermission().then(function (perm) {
            trackSafeEvent('notification_permission_result', { permission: perm });
            return perm;
        });
    }

    // ── Subscribe to push ──────────────────────────────────────
    function subscribe() {
        if (isIos() && !isStandalone()) {
            trackSafeEvent('notification_ios_pwa_required');
            return Promise.reject({
                success: false,
                is_ios_pwa_required: true,
                error: 'On iOS, please tap Share and "Add to Home Screen" first to enable notifications.'
            });
        }

        return requestPermission().then(function (permission) {
            if (permission !== 'granted') {
                return Promise.reject({ success: false, error: 'Notification permission denied' });
            }
            return getVapidPublicKey().then(function (key) {
                if (!key) throw { success: false, error: 'Push not configured on server' };
                return registerServiceWorker().then(function (reg) {
                    if (!reg || !reg.pushManager) throw { success: false, error: 'Service worker push manager unavailable' };
                    return reg.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(key)
                    }).then(function (subscription) {
                        return sendSubscriptionToServer(subscription.toJSON(), permission);
                    });
                });
            });
        }).catch(function (err) {
            console.error('[Push] Subscribe error:', err);
            trackSafeEvent('notification_subscription_failed');
            return {
                success: false,
                error: err.error || err.message || 'Subscription failed',
                is_ios_pwa_required: !!err.is_ios_pwa_required
            };
        });
    }

    function getVapidPublicKey() {
        return fetch(VAPID_KEY_URL).then(function (r) {
            if (!r.ok) throw { success: false, error: 'VAPID not configured' };
            return r.json();
        }).then(function (d) {
            if (!d.publicKey) throw { success: false, error: 'No VAPID key' };
            return d.publicKey;
        });
    }

    function sendSubscriptionToServer(sub, permissionState) {
        var meta = getPlatformMetadata();
        var payload = {
            subscription: sub,
            platform: meta.platform,
            device_type: meta.device_type,
            browser: meta.browser,
            permission_state: permissionState || 'granted'
        };

        return fetch(SUBSCRIBE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(function (r) {
            if (!r.ok) return r.json().then(function (d) { throw d; });
            trackSafeEvent('push_subscription_registered', { platform: meta.platform });
            return { success: true };
        }).catch(function (err) {
            if (err && err.error) throw err;
            return { success: false, error: 'Subscription failed' };
        });
    }

    // ── Unsubscribe ────────────────────────────────────────────
    function unsubscribe() {
        return getSubscription().then(function (sub) {
            if (!sub) return { success: true, message: 'No active subscription' };
            var endpoint = sub.endpoint;
            return sub.unsubscribe().then(function () {
                return fetch(UNSUBSCRIBE_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ endpoint: endpoint })
                }).then(function (r) {
                    trackSafeEvent('notification_disabled');
                    return { success: true };
                });
            }).catch(function (err) {
                return { success: false, error: err.message || 'Unsubscribe failed' };
            });
        });
    }

    // ── Status ──────────────────────────────────────────────────
    function getStatus() {
        if (!isSupported()) {
            return Promise.resolve({
                supported: false,
                subscribed: false,
                permission: 'denied',
                is_ios: isIos(),
                is_standalone: isStandalone(),
                requires_pwa: isIos() && !isStandalone()
            });
        }
        return getSubscription().then(function (sub) {
            return {
                supported: true,
                subscribed: !!sub,
                permission: Notification.permission || 'default',
                is_ios: isIos(),
                is_standalone: isStandalone(),
                requires_pwa: isIos() && !isStandalone()
            };
        }).catch(function () {
            return {
                supported: true,
                subscribed: false,
                permission: 'unknown',
                is_ios: isIos(),
                is_standalone: isStandalone(),
                requires_pwa: isIos() && !isStandalone()
            };
        });
    }

    // ── Toggle ──────────────────────────────────────────────────
    function toggle() {
        return getSubscription().then(function (sub) {
            if (sub) return unsubscribe();
            return subscribe();
        });
    }

    // ── Expose globally ────────────────────────────────────────
    window.PushNotifications = {
        init: getStatus,
        isSupported: isSupported,
        isStandalone: isStandalone,
        isIos: isIos,
        requestPermission: requestPermission,
        subscribe: subscribe,
        unsubscribe: unsubscribe,
        toggle: toggle,
        getStatus: getStatus,
        getSubscription: getSubscription
    };

    // ── Auto-init ──────────────────────────────────────────────
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            registerServiceWorker().then(updateBellPushStatus);
            wireProfileNudgeButton();
        });
    } else {
        registerServiceWorker().then(updateBellPushStatus);
        wireProfileNudgeButton();
    }

    function updateBellPushStatus() {
        var bell = document.getElementById('notifBell');
        if (!bell) return;
        var existing = bell.querySelector('.push-status-indicator');
        if (!existing) {
            existing = document.createElement('span');
            existing.className = 'push-status-indicator';
            existing.style.cssText = 'position:absolute;top:2px;right:2px;font-size:8px;color:#94a3b8;';
            bell.appendChild(existing);
        }
        getStatus().then(function (s) {
            if (s.subscribed) {
                existing.textContent = '🔔';
                existing.title = 'Push active';
            } else if (s.permission === 'granted') {
                existing.textContent = '📩';
                existing.title = 'Click to enable push';
            } else {
                existing.textContent = '🔕';
                existing.title = 'Push not enabled';
            }
        }).catch(function () {
            existing.textContent = '';
        });
    }

    function wireProfileNudgeButton() {
        var btn = document.getElementById('nudgeEnableNotifBtn');
        if (!btn) return;
        btn.addEventListener('click', function () {
            PushNotifications.subscribe().then(function (result) {
                if (result.success) {
                    updateBellPushStatus();
                    var card = document.getElementById('profileNudgeCard');
                    if (card) {
                        var msg = document.createElement('div');
                        msg.style.cssText = 'text-align:center;padding:0.5rem;color:#10b981;font-weight:600;';
                        msg.textContent = '✓ Notifications enabled!';
                        card.appendChild(msg);
                        setTimeout(function () { msg.remove(); }, 3000);
                    }
                } else {
                    console.warn('[Push] Subscribe failed:', result.error);
                }
            });
        });
    }
})();
