/**
 * AbhiHub In-App Notification Bell
 * Works on both mobile and laptop (browser).
 * - Fetches notifications from Supabase via /api/my-notifications
 * - Shows unread badge on bell icon
 * - Dropdown panel with recent notifications
 * - Mark single/all as read
 * - Fallback: if push is available, also subscribes to push
 */
(function () {
    'use strict';

    var _pollTimer = null;
    var _lastUnread = 0;
    var _notifOpen = false;
    var _initialized = false;

    // ── HTML Escaping helper ─────────────────────────────────────
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // ── Time formatting ──────────────────────────────────────────
    function timeAgo(iso) {
        if (!iso) return '—';
        var diff = Date.now() - new Date(iso).getTime();
        var m = Math.floor(diff / 60000);
        if (m < 1) return 'just now';
        if (m < 60) return m + 'm ago';
        var h = Math.floor(m / 60);
        if (h < 24) return h + 'h ago';
        var d = Math.floor(h / 24);
        if (d < 7) return d + 'd ago';
        return new Date(iso).toLocaleDateString();
    }

    // ── Render notifications into the dropdown ──────────────────
    function renderNotifs(items) {
        var list = document.getElementById('notifList');
        if (!list) return;
        if (!items || !items.length) {
            list.innerHTML = '<div style="text-align:center;padding:1.5rem;color:#94a3b8;">No notifications yet 🎉</div>';
            return;
        }
        list.innerHTML = items.map(function (n) {
            var typeIcon = '🔔';
            if (n.type === 'file_view') typeIcon = '👁';
            if (n.type === 'chat_message') typeIcon = '💬';
            if (n.type === 'like') typeIcon = '❤️';
            if (n.type === 'bookmark') typeIcon = '🔖';
            if (n.type === 'achievement') typeIcon = '🏆';
            var unreadClass = n.is_read ? '' : 'unread';
            var unreadDot = n.is_read ? '' : '<div class="notif-unread-dot"></div>';
            var title = escapeHtml(n.title || '');
            var msg = escapeHtml(n.message || '');
            var actionUrl = n.action_url ? escapeHtml(n.action_url) : '';
            return (
                '<div class="notif-item ' + unreadClass + '" data-notif-id="' + n.id + '" data-action-url="' + actionUrl + '" style="cursor:pointer;">' +
                    '<div class="notif-item-icon default">' + typeIcon + '</div>' +
                    '<div class="notif-item-content">' +
                        '<div class="notif-item-title">' + title + '</div>' +
                        '<div class="notif-item-message">' + msg + '</div>' +
                        '<div class="notif-item-time">' + timeAgo(n.created_at) + '</div>' +
                    '</div>' +
                    unreadDot +
                '</div>'
            );
        }).join('');
    }


    // ── Update unread badge ─────────────────────────────────────
    function updateBadge(unread) {
        _lastUnread = unread || 0;
        var badge = document.getElementById('notifBadge');
        if (!badge) return;
        if (_lastUnread > 0) {
            badge.style.display = 'block';
            badge.textContent = _lastUnread > 9 ? '9+' : String(_lastUnread);
        } else {
            badge.style.display = 'none';
        }
    }

    // ── Fetch notifications from API ────────────────────────────
    function fetchNotifications(render) {
        render = render !== false;
        var xhr = null;
        try {
            if (window.fetch) {
                xhr = fetch('/api/my-notifications?limit=20', {
                    signal: AbortSignal.timeout ? AbortSignal.timeout(8000) : undefined
                }).then(function (r) { return r.json(); });
            } else {
                // Fallback for older browsers
                xhr = new Promise(function (resolve) {
                    var req = new XMLHttpRequest();
                    req.open('GET', '/api/my-notifications?limit=20', true);
                    req.onload = function () { resolve(JSON.parse(req.responseText)); };
                    req.onerror = function () { resolve({ success: false }); };
                    req.timeout = 8000;
                    req.ontimeout = function () { resolve({ success: false }); };
                    req.send();
                });
            }
        } catch (e) {
            return;
        }
        xhr.then(function (d) {
            if (!d || !d.success) return;
            updateBadge(d.unread || 0);
            if (render) _renderInDOM(d.data || []);
        }).catch(function () {});
    }

    function _renderInDOM(items) {
        renderNotifs(items);
    }

    // ── Toggle panel ────────────────────────────────────────────
    function togglePanel() {
        var panel = document.getElementById('notifPanel');
        var bell = document.getElementById('notifBell');
        if (!panel) return;
        _notifOpen = !_notifOpen;
        panel.style.display = _notifOpen ? 'block' : 'none';
        if (bell) bell.setAttribute('aria-expanded', String(_notifOpen));
        if (_notifOpen) {
            fetchNotifications(true);
            // Track in GA if available
            if (window.AbhiHubTracking && window.AbhiHubTracking.trackNotificationOpen) {
                window.AbhiHubTracking.trackNotificationOpen(_lastUnread);
            }
        }
    }

    // ── Mark single notification read ───────────────────────────
    function markRead(notifId) {
        if (!notifId) return;
        var xhr;
        try {
            if (window.fetch) {
                xhr = fetch('/api/notifications/' + notifId + '/read', { method: 'POST' })
                    .then(function (r) { return r.ok; });
            } else {
                xhr = new Promise(function (resolve) {
                    var req = new XMLHttpRequest();
                    req.open('POST', '/api/notifications/' + notifId + '/read', true);
                    req.onload = function () { resolve(req.status === 200); };
                    req.onerror = function () { resolve(false); };
                    req.send();
                });
            }
        } catch (e) { return; }
        xhr.then(function (ok) {
            if (!ok) return;
            var item = document.querySelector('.notif-item[data-notif-id="' + notifId + '"]');
            if (item) {
                item.classList.remove('unread');
                item.setAttribute('data-read', 'true');
                var dot = item.querySelector('.notif-unread-dot');
                if (dot) dot.remove();
            }
            if (_lastUnread > 0) updateBadge(_lastUnread - 1);
        }).catch(function () {});
    }

    // ── Mark all read ───────────────────────────────────────────
    function markAllRead() {
        var xhr;
        try {
            if (window.fetch) {
                xhr = fetch('/api/my-notifications/read', { method: 'POST' })
                    .then(function (r) { return r.ok ? r.json() : Promise.reject(); });
            } else {
                xhr = new Promise(function (resolve) {
                    var req = new XMLHttpRequest();
                    req.open('POST', '/api/my-notifications/read', true);
                    req.onload = function () { resolve(req.status === 200 ? JSON.parse(req.responseText) : false); };
                    req.onerror = function () { resolve(false); };
                    req.send();
                });
            }
        } catch (e) { return; }
        xhr.then(function (d) {
            if (!d || !d.success) return;
            updateBadge(0);
            fetchNotifications(true);
        }).catch(function () {});
    }

    // ── Close panel on outside click ────────────────────────────
    function onDocumentClick(e) {
        var wrap = document.getElementById('notifBellWrap');
        if (wrap && !wrap.contains(e.target) && _notifOpen) {
            _notifOpen = false;
            var panel = document.getElementById('notifPanel');
            var bell = document.getElementById('notifBell');
            if (panel) panel.style.display = 'none';
            if (bell) bell.setAttribute('aria-expanded', 'false');
        }
    }

    // ── Chat message → create in-app notification ───────────────
    // Called by chat.js when a message arrives
    window.AbhiHubOnChatMessage = function (senderName, peerId) {
        // Create a lightweight in-app notification for this user
        // We do this client-side only; a full implementation would POST to server
        // For now, just ensure badge updates on next poll
        if (_notifOpen) {
            // Refresh to pick up any new notifications
            fetchNotifications(true);
        }
    };

    // ── Initialize ──────────────────────────────────────────────
    function init() {
        if (_initialized) return;
        _initialized = true;

        var bell = document.getElementById('notifBell');
        if (!bell) return;

        bell.addEventListener('click', togglePanel);

        // Wire up "Mark all read" button
        var markAllBtn = document.querySelector('[data-action="markAllRead"]');
        if (markAllBtn) markAllBtn.addEventListener('click', markAllRead);

        // Wire up individual notification click → mark read + navigate
        var list = document.getElementById('notifList');
        if (list) {
            list.addEventListener('click', function (e) {
                var item = e.target.closest('.notif-item');
                if (item && item.getAttribute('data-notif-id')) {
                    var notifId = item.getAttribute('data-notif-id');
                    var actionUrl = item.getAttribute('data-action-url');
                    markRead(notifId);
                    if (actionUrl && actionUrl.startsWith('/') && !actionUrl.startsWith('//') && !actionUrl.includes('\\')) {
                        setTimeout(function () { window.location.href = actionUrl; }, 150);
                    }
                }
            });
        }


        document.addEventListener('click', onDocumentClick);

        // Initial fetch + poll
        if (window.__CURRENT_USER__ && window.__CURRENT_USER__.uid) {
            fetchNotifications(true);
            // Poll every 60s (sensible interval; 10min was too infrequent)
            _pollTimer = setInterval(function () { fetchNotifications(true); }, 60 * 1000);
        }

        // Also try to init push notifications if supported
        tryInitPush();
    }

    // ── Push notification init (optional, for browsers that support it) ──
    function tryInitPush() {
        if (!window.PushNotifications) return;
        if (!window.PushNotifications.isSupported()) return;
        // Don't auto-subscribe — wait for user gesture (click "Enable notifications")
        // Wire up the "Enable push" button in the bell panel
        var enableBtn = document.getElementById('notifEnablePushBtn');
        if (enableBtn) {
            enableBtn.addEventListener('click', function () {
                PushNotifications.subscribe().then(function (result) {
                    if (result.success) {
                        enableBtn.textContent = '🔔 Push active';
                        enableBtn.disabled = true;
                        // Refresh notification list
                        fetchNotifications(true);
                    } else {
                        console.warn('[Push] Subscribe failed:', result.error);
                        enableBtn.textContent = result.error || 'Failed';
                        setTimeout(function () { enableBtn.textContent = '🔕 Enable push'; }, 3000);
                    }
                });
            });
        }
    }

    // Kick off when DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
