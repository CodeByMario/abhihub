/**
 * AbhiHub Push Notification Client
 * Handles push notification subscription and permission management.
 * Works on both mobile (via browser notifications) and laptop/desktop (via service worker push).
 */
(function () {
    'use strict';

    var VAPID_KEY_URL = '/api/push/vapid-public-key';
    var SUBSCRIBE_URL = '/api/push/subscribe';
    var UNSUBSCRIBE_URL = '/api/push/unsubscribe';
    var STATUS_URL = '/api/push/status';

    var _swReg = null;
    var _initialized = false;

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

    // ── Service Worker registration ─────────────────────────────
    function registerServiceWorker() {
        if (_swReg) return Promise.resolve(_swReg);
        if (!('serviceWorker' in navigator)) return Promise.resolve(null);
        return navigator.serviceWorker.register('/static/js/service-worker.js', {
            scope: '/'
        }).then(function (reg) {
            _swReg = reg;
            console.log('[Push] Service worker registered');
            return reg;
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
        return Notification.requestPermission();
    }

    // ── Subscribe to push ──────────────────────────────────────
    function subscribe() {
        return requestPermission().then(function (permission) {
            if (permission !== 'granted') {
                return Promise.reject({ success: false, error: 'Notification permission denied' });
            }
            return getVapidPublicKey().then(function (key) {
                if (!key) throw { success: false, error: 'Push not configured on server' };
                return registerServiceWorker().then(function (reg) {
                    if (!reg || !reg.pushManager) throw { success: false, error: 'SW not available' };
                    return reg.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(key)
                    }).then(function (subscription) {
                        return sendSubscriptionToServer(subscription.toJSON());
                    });
                });
            });
        }).catch(function (err) {
            console.error('[Push] Subscribe error:', err);
            return { success: false, error: err.message || 'Subscription failed' };
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

    function sendSubscriptionToServer(sub) {
        return fetch(SUBSCRIBE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subscription: sub })
        }).then(function (r) {
            if (!r.ok) return r.json().then(function (d) { throw d; });
            return { success: true };
        }).catch(function (err) {
            if (err && err.error) throw err;
            return { success: false, error: 'Subscription failed' };
        });
    }

    // ── Unsubscribe ────────────────────────────────────────────
    function unsubscribe() {
        return getSubscription().then(function (sub) {
            if (!sub) return { success: false, error: 'No subscription' };
            return sub.unsubscribe().then(function () {
                return fetch(UNSUBSCRIBE_URL, { method: 'DELETE' }).then(function (r) {
                    if (r.ok) return { success: true };
                    return { success: false, error: 'Unsubscribe API failed' };
                });
            }).catch(function (err) {
                return { success: false, error: err.message || 'Unsubscribe failed' };
            });
        });
    }

    // ── Status ──────────────────────────────────────────────────
    function getStatus() {
        if (!isSupported()) return Promise.resolve({ supported: false, subscribed: false, permission: 'denied' });
        return getSubscription().then(function (sub) {
            return {
                supported: true,
                subscribed: !!sub,
                permission: Notification.permission || 'default'
            };
        }).catch(function () {
            return { supported: true, subscribed: false, permission: 'unknown' };
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
        isSupported: isSupported,
        requestPermission: requestPermission,
        subscribe: subscribe,
        unsubscribe: unsubscribe,
        toggle: toggle,
        getStatus: getStatus,
        getSubscription: getSubscription
    };

    // ── Auto-init (don't request permission automatically) ─────
    // Just register SW silently; permission prompt comes from user action
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            registerServiceWorker().then(function () {
                // Update bell UI if it exists
                updateBellPushStatus();
            });
        });
    } else {
        registerServiceWorker().then(updateBellPushStatus);
    }

    // ── Update bell UI to show push status ─────────────────────
    function updateBellPushStatus() {
        var bell = document.getElementById('notifBell');
        if (!bell) return;
        // Add push subscription status indicator
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

    // ── Wire "Enable notifications" button in profile nudge ────
    function wireProfileNudgeButton() {
        var btn = document.getElementById('nudgeEnableNotifBtn');
        if (!btn) return;
        btn.addEventListener('click', function () {
            PushNotifications.subscribe().then(function (result) {
                if (result.success) {
                    // Update bell indicator
                    updateBellPushStatus();
                    // Optionally show a small confirmation
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

    // Wire up on load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wireProfileNudgeButton);
    } else {
        wireProfileNudgeButton();
    }
})();
