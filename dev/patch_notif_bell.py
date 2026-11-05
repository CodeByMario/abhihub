"""
Patch notification-bell.js to pause polling when tab is hidden.
"""
import os

path = os.path.join('static', 'js', 'notification-bell.js')
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target = """        // Initial fetch + poll
        if (window.__CURRENT_USER__ && window.__CURRENT_USER__.uid) {
            fetchNotifications(true);
            // Poll every 60s (sensible interval; 10min was too infrequent)
            _pollTimer = setInterval(function () { fetchNotifications(true); }, 60 * 1000);
        }"""

replacement = """        // Initial fetch + visibility-aware polling
        if (window.__CURRENT_USER__ && window.__CURRENT_USER__.uid) {
            fetchNotifications(true);
            // Poll every 60s only when document is actively visible
            _pollTimer = setInterval(function () {
                if (!document.hidden) {
                    fetchNotifications(true);
                }
            }, 60 * 1000);

            // Refetch when user returns to tab after being hidden
            document.addEventListener('visibilitychange', function () {
                if (!document.hidden) {
                    fetchNotifications(false);
                }
            });
        }"""

if target in content:
    content = content.replace(target, replacement, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched notification-bell.js with visibility-aware polling")
else:
    print("Target not found in notification-bell.js")
