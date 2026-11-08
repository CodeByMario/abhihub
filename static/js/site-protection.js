(function () {
    'use strict';

    function currentIdentity() {
        var user = window.__CURRENT_USER__ || {};
        return {
            email: String(user.email || '').trim(),
            studentId: String(user.registrationNumber || user.studentId || user.uid || '').trim()
        };
    }

    function addPersonalMenu(identity) {
        // If security.js custom contextmenu handles the event, avoid rendering duplicate overlapping menu
        if (window.__ABHIHUB_SECURITY_LOADED__ || document.getElementById('abhihub-custom-contextmenu')) {
            return;
        }

        var menu = document.createElement('div');
        menu.className = 'abhihub-context-menu';
        menu.id = 'abhihub-personal-context-menu';
        menu.setAttribute('role', 'dialog');
        menu.setAttribute('aria-label', 'AbhiHub personalized information');
        menu.hidden = true;

        var title = document.createElement('p');
        title.className = 'abhihub-context-menu-title';
        title.textContent = 'AbhiHub · Account Profile';
        menu.appendChild(title);

        [
            ['Email', identity.email || 'Guest'],
            ['Student ID', identity.studentId || 'Not available']
        ].forEach(function (entry) {
            var row = document.createElement('p');
            row.className = 'abhihub-context-menu-row';
            row.textContent = entry[0] + ': ' + entry[1];
            menu.appendChild(row);
        });

        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'abhihub-context-menu-close';
        close.textContent = 'Close';
        close.addEventListener('click', hideMenu);
        menu.appendChild(close);
        document.body.appendChild(menu);

        function hideMenu() { menu.hidden = true; }
        function showMenu(x, y) {
            if (window.__ABHIHUB_SECURITY_LOADED__ || document.getElementById('abhihub-custom-contextmenu')) {
                menu.hidden = true;
                return;
            }
            menu.hidden = false;
            menu.style.visibility = 'hidden';
            var rect = menu.getBoundingClientRect();
            var pad = 12;
            var posX = Math.max(pad, Math.min(x, window.innerWidth - rect.width - pad));
            var posY = Math.max(pad, Math.min(y, window.innerHeight - rect.height - pad));
            menu.style.left = posX + 'px';
            menu.style.top = posY + 'px';
            menu.style.visibility = 'visible';
            close.focus({ preventScroll: true });
        }

        function isEditable(target) {
            return !!target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]');
        }

        document.addEventListener('contextmenu', function (event) {
            if (window.__ABHIHUB_SECURITY_LOADED__) return;
            if (isEditable(event.target)) return;
            event.preventDefault();
            showMenu(event.clientX, event.clientY);
        });
        document.addEventListener('keydown', function (event) {
            if (window.__ABHIHUB_SECURITY_LOADED__) return;
            if ((event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) && !isEditable(event.target)) {
                event.preventDefault();
                var rect = event.target.getBoundingClientRect();
                showMenu(rect.left, rect.bottom);
            } else if (event.key === 'Escape') hideMenu();
        });
        document.addEventListener('pointerdown', function (event) {
            if (!menu.hidden && !menu.contains(event.target)) hideMenu();
        });
    }

    function initialize() {
        var identity = currentIdentity();
        addPersonalMenu(identity);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
    else initialize();
})();
