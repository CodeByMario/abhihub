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
        var menu = document.createElement('div');
        menu.className = 'abhihub-context-menu';
        menu.id = 'abhihub-personal-context-menu';
        menu.setAttribute('role', 'dialog');
        menu.setAttribute('aria-label', 'AbhiHub personalized information');
        menu.hidden = true;

        var title = document.createElement('p');
        title.className = 'abhihub-context-menu-title';
        title.textContent = 'AbhiHub · Personalized view';
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
            menu.hidden = false;
            var rect = menu.getBoundingClientRect();
            menu.style.left = Math.max(8, Math.min(x, window.innerWidth - rect.width - 8)) + 'px';
            menu.style.top = Math.max(8, Math.min(y, window.innerHeight - rect.height - 8)) + 'px';
            close.focus({ preventScroll: true });
        }

        function isEditable(target) {
            return !!target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]');
        }

        document.addEventListener('contextmenu', function (event) {
            if (isEditable(event.target)) return;
            event.preventDefault();
            showMenu(event.clientX, event.clientY);
        });
        document.addEventListener('keydown', function (event) {
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
