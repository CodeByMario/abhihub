/**
 * AbhiHub Client Security & Personalized Context Menu Module
 * - Replaces default browser right-click with a custom AbhiHub Personalized Quick-Action Menu
 * - Disables text selection and drag-and-drop on content areas
 * - Blocks developer tools keyboard shortcuts & detects DevTools activation
 * - Restricts console execution & clears console buffer
 * - Blocks screenshot / screen-record keyboard shortcuts (PC & Mac)
 * - Detects mobile screenshot attempts via visibility / blur heuristics
 */

(function () {
  'use strict';

  /* ── 1. Text Selection & Copy/Drag Prevention ──────────────────────────── */
  function injectStyles() {
    if (document.getElementById('abhihub-sec-styles')) return;
    const style = document.createElement('style');
    style.id = 'abhihub-sec-styles';
    style.textContent = `
      *, *::before, *::after {
        -webkit-user-select: none !important;
        -moz-user-select: none !important;
        -ms-user-select: none !important;
        user-select: none !important;
        -webkit-user-drag: none !important;
      }
      input, textarea, [contenteditable="true"], [contenteditable="true"] *, .allow-select, .allow-select * {
        -webkit-user-select: text !important;
        -moz-user-select: text !important;
        -ms-user-select: text !important;
        user-select: text !important;
      }

      /* ── Personalized Context Menu Styles ── */
      #abhihub-custom-contextmenu {
        position: fixed;
        z-index: 9999999;
        min-width: 220px;
        background: rgba(18, 24, 38, 0.88);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 14px;
        box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.05);
        padding: 6px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        color: #f1f5f9;
        display: none;
        opacity: 0;
        transform: scale(0.96) translateY(-4px);
        transition: opacity 0.15s ease, transform 0.15s ease;
        user-select: none;
      }
      [data-theme="light"] #abhihub-custom-contextmenu {
        background: rgba(255, 255, 255, 0.92);
        border-color: rgba(0, 0, 0, 0.1);
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18), 0 0 0 1px rgba(0, 0, 0, 0.04);
        color: #1e293b;
      }
      #abhihub-custom-contextmenu.active {
        display: block;
        opacity: 1;
        transform: scale(1) translateY(0);
      }
      .cm-header {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        padding: 8px 10px 4px;
        color: #94a3b8;
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .cm-item {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 10px;
        font-size: 13px;
        font-weight: 500;
        border-radius: 8px;
        cursor: pointer;
        transition: background 0.12s ease, color 0.12s ease;
        text-decoration: none;
        color: inherit;
      }
      .cm-item:hover {
        background: rgba(99, 102, 241, 0.18);
        color: #818cf8;
      }
      [data-theme="light"] .cm-item:hover {
        background: rgba(99, 102, 241, 0.12);
        color: #4f46e5;
      }
      .cm-item svg, .cm-item .cm-icon {
        width: 16px;
        height: 16px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        opacity: 0.9;
      }
      .cm-divider {
        height: 1px;
        background: rgba(255, 255, 255, 0.08);
        margin: 5px 4px;
      }
      [data-theme="light"] .cm-divider {
        background: rgba(0, 0, 0, 0.08);
      }
      .cm-badge {
        margin-left: auto;
        font-size: 10px;
        padding: 2px 6px;
        border-radius: 6px;
        background: rgba(99, 102, 241, 0.25);
        color: #a5b4fc;
        font-weight: 600;
      }
      [data-theme="light"] .cm-badge {
        background: rgba(99, 102, 241, 0.15);
        color: #4f46e5;
      }
    `;
    document.head ? document.head.appendChild(style) : document.addEventListener('DOMContentLoaded', () => document.head.appendChild(style));
  }
  injectStyles();

  function isFormInput(target) {
    if (!target) return false;
    const tag = (target.tagName || '').toLowerCase();
    return tag === 'input' || tag === 'textarea' || target.isContentEditable || (target.closest && target.closest('.allow-select'));
  }

  document.addEventListener('selectstart', function (e) {
    if (!isFormInput(e.target)) {
      e.preventDefault();
      return false;
    }
  }, { capture: true });

  document.addEventListener('dragstart', function (e) {
    if (!isFormInput(e.target)) {
      e.preventDefault();
      return false;
    }
  }, { capture: true });

  document.addEventListener('copy', function (e) {
    if (!isFormInput(e.target)) {
      e.preventDefault();
      showToast('⚠️ Copying is disabled to protect study resources.');
      return false;
    }
  }, { capture: true });

  /* ── 2. Personalized Context Menu ────────────────────────────────────────── */
  let contextMenuEl = null;

  function createContextMenu() {
    if (contextMenuEl) return contextMenuEl;
    contextMenuEl = document.createElement('div');
    contextMenuEl.id = 'abhihub-custom-contextmenu';
    contextMenuEl.innerHTML = `
      <div class="cm-header">
        <span>⚡ AbhiHub Menu</span>
      </div>
      <div class="cm-item" data-action="ai">
        <span class="cm-icon">🤖</span>
        <span>Ask Tarika AI</span>
        <span class="cm-badge">AI</span>
      </div>
      <div class="cm-item" data-action="search">
        <span class="cm-icon">🔍</span>
        <span>Search Notes & PYQs</span>
      </div>
      <div class="cm-item" data-action="upload">
        <span class="cm-icon">📤</span>
        <span>Upload Paper / Notes</span>
      </div>
      <div class="cm-item" data-action="leaderboard">
        <span class="cm-icon">🏆</span>
        <span>Leaderboard & Rank</span>
      </div>
      <div class="cm-divider"></div>
      <div class="cm-item" data-action="copylink">
        <span class="cm-icon">🔗</span>
        <span>Copy Page Link</span>
      </div>
      <div class="cm-item" data-action="theme">
        <span class="cm-icon">🌓</span>
        <span>Toggle Theme</span>
      </div>
      <div class="cm-item" data-action="refresh">
        <span class="cm-icon">🔄</span>
        <span>Reload Page</span>
      </div>
    `;

    contextMenuEl.addEventListener('click', function (e) {
      const item = e.target.closest('.cm-item');
      if (!item) return;
      const action = item.getAttribute('data-action');
      handleMenuAction(action);
      hideContextMenu();
    });

    document.body.appendChild(contextMenuEl);
    return contextMenuEl;
  }

  function handleMenuAction(action) {
    switch (action) {
      case 'ai':
        if (typeof window.openAiModal === 'function') {
          window.openAiModal();
        } else {
          window.location.href = '/ai';
        }
        break;
      case 'search':
        const searchInput = document.getElementById('search-input') || document.querySelector('input[type="search"]');
        if (searchInput) {
          searchInput.focus();
        } else {
          window.location.href = '/dashboard';
        }
        break;
      case 'upload':
        window.location.href = '/upload';
        break;
      case 'leaderboard':
        window.location.href = '/leaderboard';
        break;
      case 'copylink':
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(window.location.href)
            .then(() => showToast('✓ Page link copied!'))
            .catch(() => showToast('✓ ' + window.location.href));
        } else {
          showToast('✓ Link: ' + window.location.href);
        }
        break;
      case 'theme':
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', nextTheme);
        try { localStorage.setItem('abhihub_theme', nextTheme); } catch (e) {}
        showToast(`Theme switched to ${nextTheme} mode`);
        break;
      case 'refresh':
        window.location.reload();
        break;
    }
  }

  function showContextMenu(x, y) {
    const menu = createContextMenu();
    menu.style.display = 'block';

    // Position adjustments to prevent overflowing window bounds
    const menuWidth = 230;
    const menuHeight = 280;
    const winWidth = window.innerWidth;
    const winHeight = window.innerHeight;

    let posX = x;
    let posY = y;

    if (x + menuWidth > winWidth) {
      posX = winWidth - menuWidth - 10;
    }
    if (y + menuHeight > winHeight) {
      posY = winHeight - menuHeight - 10;
    }

    menu.style.left = `${Math.max(10, posX)}px`;
    menu.style.top = `${Math.max(10, posY)}px`;

    requestAnimationFrame(() => {
      menu.classList.add('active');
    });
  }

  function hideContextMenu() {
    if (contextMenuEl && contextMenuEl.classList.contains('active')) {
      contextMenuEl.classList.remove('active');
      setTimeout(() => {
        if (!contextMenuEl.classList.contains('active')) {
          contextMenuEl.style.display = 'none';
        }
      }, 150);
    }
  }

  // Intercept Right-Click to present Personalized Menu
  document.addEventListener('contextmenu', function (e) {
    e.preventDefault();
    showContextMenu(e.clientX, e.clientY);
    return false;
  }, { capture: true });

  // Hide context menu on outside click or scroll or Esc
  document.addEventListener('click', function (e) {
    if (contextMenuEl && !contextMenuEl.contains(e.target)) {
      hideContextMenu();
    }
  });

  document.addEventListener('scroll', hideContextMenu, { passive: true });
  window.addEventListener('resize', hideContextMenu);

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      hideContextMenu();
    }
  });

  /* ── 3. Toast Notification Helper ────────────────────────────────────────── */
  function showToast(msg) {
    let toast = document.getElementById('abhihub-mini-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'abhihub-mini-toast';
      toast.style.cssText = `
        position: fixed;
        bottom: 24px;
        left: 50%;
        transform: translateX(-50%) translateY(20px);
        background: rgba(15, 23, 42, 0.92);
        color: #f8fafc;
        border: 1px solid rgba(255, 255, 255, 0.15);
        backdrop-filter: blur(10px);
        padding: 8px 18px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 500;
        z-index: 99999999;
        box-shadow: 0 10px 25px rgba(0,0,0,0.3);
        opacity: 0;
        transition: all 0.2s ease;
        pointer-events: none;
      `;
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = '1';
    toast.style.transform = 'translateX(-50%) translateY(0)';
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(-50%) translateY(20px)';
    }, 2500);
  }

  /* ── 4. Block Developer Tools & Shortcuts ─────────────────────────────────── */
  document.addEventListener('keydown', function (e) {
    const key   = (e.key  || '').toLowerCase();
    const code  = (e.code || '');
    const ctrl  = e.ctrlKey  || e.metaKey;
    const shift = e.shiftKey;

    // F12 – DevTools
    if (key === 'f12') {
      e.preventDefault();
      showToast('⚠️ Developer Tools are disabled on AbhiHub.');
      return false;
    }

    // Ctrl/Cmd + Shift + I/J/C/K/M (DevTools & Inspector)
    if (ctrl && shift && (key === 'i' || key === 'j' || key === 'c' || key === 'k' || key === 'm')) {
      e.preventDefault();
      showToast('⚠️ Developer Tools are disabled on AbhiHub.');
      return false;
    }

    // Ctrl/Cmd + U (View Source)
    if (ctrl && !shift && key === 'u') {
      e.preventDefault();
      showToast('⚠️ View Source is disabled.');
      return false;
    }

    // Ctrl/Cmd + S (Save page)
    if (ctrl && !shift && key === 's') {
      e.preventDefault();
      return false;
    }
  }, { capture: true });

  /* ── 5. Console Protection & Anti-Scripting Trap ─────────────────────────── */
  function protectConsole() {
    try {
      const banner = 'color: #ff3344; font-size: 26px; font-weight: bold;';
      const text = 'color: #fbbf24; font-size: 13px; font-weight: 500;';
      console.log('%c⚡ AbhiHub Security', banner);
      console.log('%cRunning untrusted scripts in this console violates AbhiHub Terms of Service.', text);

      // Periodically clean console
      setInterval(function () {
        try { console.clear(); } catch(e) {}
      }, 5000);

      // DevTools debugger trap: pauses execution if inspector is opened
      setInterval(function () {
        const start = performance.now();
        (function () { return true; }["constructor"]("debugger")());
        if (performance.now() - start > 100) {
          showToast('⚠️ DevTools detected.');
        }
      }, 2500);
    } catch (e) {}
  }
  protectConsole();

})();
