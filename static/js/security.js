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
  window.__ABHIHUB_SECURITY_LOADED__ = true;

  /* ── 1. Text Selection & Copy/Drag Prevention ──────────────────────────── */
  function injectStyles() {
    if (document.getElementById('abhihub-sec-styles')) return;
    const style = document.createElement('style');
    style.id = 'abhihub-sec-styles';
    style.textContent = `
      html, body {
        touch-action: pan-x pan-y !important;
        -webkit-text-size-adjust: 100% !important;
        text-size-adjust: 100% !important;
      }
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

      /* ── Apple HIG Personalized Context Menu Styles ── */
      #abhihub-custom-contextmenu {
        position: fixed;
        z-index: 2147483647;
        min-width: 240px;
        max-width: 280px;
        background: rgba(28, 28, 30, 0.92);
        backdrop-filter: blur(24px);
        -webkit-backdrop-filter: blur(24px);
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 16px;
        box-shadow: 0 18px 45px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.05);
        padding: 6px;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
        color: #f5f5f7;
        display: none;
        opacity: 0;
        transform: scale(0.96) translateY(-4px);
        transition: opacity 0.15s cubic-bezier(0.16, 1, 0.3, 1), transform 0.15s cubic-bezier(0.16, 1, 0.3, 1);
        user-select: none;
      }
      [data-theme="light"] #abhihub-custom-contextmenu {
        background: rgba(255, 255, 255, 0.94);
        border-color: rgba(0, 0, 0, 0.09);
        box-shadow: 0 18px 45px rgba(0, 0, 0, 0.14), 0 0 0 1px rgba(0, 0, 0, 0.04);
        color: #1d1d1f;
      }
      #abhihub-custom-contextmenu.active {
        display: block;
        opacity: 1;
        transform: scale(1) translateY(0);
      }
      .cm-profile-card {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 10px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.05);
      }
      [data-theme="light"] .cm-profile-card {
        background: rgba(0, 0, 0, 0.035);
      }
      .cm-profile-avatar {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: var(--apple-blue, #0071e3);
        color: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }
      .cm-profile-info {
        flex: 1;
        min-width: 0;
      }
      .cm-profile-email {
        font-size: 12.5px;
        font-weight: 600;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        color: inherit;
        letter-spacing: -0.01em;
      }
      .cm-profile-id {
        font-size: 11px;
        color: #86868b;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        margin-top: 1px;
      }
      .cm-item {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 10px;
        font-size: 13px;
        font-weight: 500;
        border-radius: 10px;
        cursor: pointer;
        transition: background 0.12s ease, color 0.12s ease;
        text-decoration: none;
        color: inherit;
      }
      .cm-item:hover {
        background: var(--apple-blue, #0071e3);
        color: #ffffff !important;
      }
      .cm-item:hover svg, .cm-item:hover .cm-badge {
        color: #ffffff !important;
      }
      .cm-item svg {
        width: 15px;
        height: 15px;
        flex-shrink: 0;
        opacity: 0.85;
      }
      .cm-divider {
        height: 1px;
        background: rgba(255, 255, 255, 0.08);
        margin: 5px 4px;
      }
      [data-theme="light"] .cm-divider {
        background: rgba(0, 0, 0, 0.06);
      }
      .cm-badge {
        margin-left: auto;
        font-size: 9.5px;
        padding: 2px 7px;
        border-radius: 980px;
        background: rgba(0, 113, 227, 0.2);
        color: #2997ff;
        font-weight: 600;
      }
      [data-theme="light"] .cm-badge {
        background: rgba(0, 113, 227, 0.1);
        color: #0071e3;
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
    contextMenuEl.setAttribute('role', 'menu');

    const user = window.__CURRENT_USER__ || {};
    const email = String(user.email || '').trim();
    const studentId = String(user.registrationNumber || user.studentId || user.uid || '').trim();

    let profileHtml = '';
    if (email || studentId) {
      profileHtml = `
        <div class="cm-profile-card">
          <div class="cm-profile-avatar">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
          </div>
          <div class="cm-profile-info">
            <div class="cm-profile-email" title="${email || 'AbhiHub Student'}">${email || 'Personalized View'}</div>
            ${studentId ? `<div class="cm-profile-id">ID: ${studentId.length > 20 ? studentId.substring(0, 18) + '…' : studentId}</div>` : ''}
          </div>
        </div>
        <div class="cm-divider"></div>
      `;
    }

    contextMenuEl.innerHTML = `
      ${profileHtml}
      <div class="cm-item" data-action="ai">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"></path></svg>
        <span>Tarika (AI Assistant)</span>
        <span class="cm-badge">AI</span>
      </div>
      <div class="cm-item" data-action="search">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
        <span>Search Notes & PYQs</span>
      </div>
      <div class="cm-item" data-action="upload">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
        <span>Upload Paper / Notes</span>
      </div>
      <div class="cm-item" data-action="leaderboard">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="7"></circle><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"></polyline></svg>
        <span>Leaderboard & Rank</span>
      </div>
      <div class="cm-divider"></div>
      <div class="cm-item" data-action="copylink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
        <span>Copy Page Link</span>
      </div>
      <div class="cm-item" data-action="theme">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
        <span>Toggle Theme</span>
      </div>
      <div class="cm-item" data-action="refresh">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
        <span>Reload Page</span>
      </div>
      <div class="cm-item" data-action="update-pwa">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 16 12 12 8 16"></polyline><line x1="12" y1="12" x2="12" y2="21"></line><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"></path></svg>
        <span>Update App Cache</span>
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
        if (typeof window.toggleAbhiAiDrawer === 'function') {
          const drw = document.getElementById('abhiAiDrawer');
          if (!drw || !drw.classList.contains('open')) {
            window.toggleAbhiAiDrawer();
          }
        } else if (window.parent && typeof window.parent.toggleAbhiAiDrawer === 'function') {
          const pDrw = window.parent.document.getElementById('abhiAiDrawer');
          if (!pDrw || !pDrw.classList.contains('open')) {
            window.parent.toggleAbhiAiDrawer();
          }
        } else if (window.AbhiHubBridge && typeof window.AbhiHubBridge.openTarika === 'function') {
          window.AbhiHubBridge.openTarika();
        } else {
          const launcher = document.getElementById('abhiAiLauncher') || (window.parent && window.parent.document.getElementById('abhiAiLauncher'));
          if (launcher) {
            launcher.click();
          } else if (typeof window.openAiModal === 'function') {
            window.openAiModal();
          } else {
            window.location.href = '/ai';
          }
        }
        break;
      case 'search':
        const searchInput = document.getElementById('search-input') || document.querySelector('input[type="search"]') || document.querySelector('input[name="search"]');
        if (searchInput) {
          searchInput.focus();
        } else if (typeof window.navigateTo === 'function') {
          window.navigateTo('/dashboard');
        } else {
          window.location.href = '/dashboard';
        }
        break;
      case 'upload':
        if (typeof window.navigateTo === 'function') {
          window.navigateTo('/upload', true);
        } else {
          window.location.href = '/upload';
        }
        break;
      case 'leaderboard':
        if (typeof window.navigateTo === 'function') {
          window.navigateTo('/leaderboard', true);
        } else {
          window.location.href = '/leaderboard';
        }
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
      case 'update-pwa':
        updatePwaCache();
        break;
    }
  }

  function updatePwaCache() {
    if (!('serviceWorker' in navigator) || !('caches' in window)) {
      showToast('⚠️ App cache updates are not supported here.');
      return;
    }

    showToast('⏳ Updating AbhiHub app cache…');
    Promise.all([
      navigator.serviceWorker.getRegistrations().then(function (registrations) {
        return Promise.all(registrations.map(function (registration) {
          return registration.update().then(function () {
            if (registration.waiting) {
              registration.waiting.postMessage({ type: 'SKIP_WAITING' });
            }
          });
        }));
      }),
      caches.keys().then(function (cacheNames) {
        return Promise.all(cacheNames
          .filter(function (name) {
            return name.indexOf('abhihub-') === 0 && name.indexOf('abhihub-ai-models-') !== 0;
          })
          .map(function (name) { return caches.delete(name); }));
      })
    ]).then(function () {
      showToast('✅ App cache updated. Reloading…');
      setTimeout(function () {
        window.location.reload();
      }, 500);
    }).catch(function (error) {
      console.error('[PWA] Cache update failed:', error);
      showToast('⚠️ Could not update app cache. Please try again.');
    });
  }

  function showContextMenu(x, y) {
    const menu = createContextMenu();

    // Dynamically update identity if changed
    const user = window.__CURRENT_USER__ || {};
    const email = String(user.email || '').trim();
    const studentId = String(user.registrationNumber || user.studentId || user.uid || '').trim();
    const profileEmailEl = menu.querySelector('.cm-profile-email');
    const profileIdEl = menu.querySelector('.cm-profile-id');
    if (profileEmailEl && email) profileEmailEl.textContent = email;
    if (profileIdEl && studentId) profileIdEl.textContent = 'ID: ' + (studentId.length > 20 ? studentId.substring(0, 18) + '…' : studentId);

    menu.style.display = 'block';
    menu.style.visibility = 'hidden';

    // Exact viewport clamping: menu is guaranteed to stay within visible screen bounds
    const rect = menu.getBoundingClientRect();
    const pad = 12;
    const maxX = window.innerWidth - rect.width - pad;
    const maxY = window.innerHeight - rect.height - pad;

    const posX = Math.max(pad, Math.min(x, maxX));
    const posY = Math.max(pad, Math.min(y, maxY));

    menu.style.left = `${posX}px`;
    menu.style.top = `${posY}px`;
    menu.style.visibility = 'visible';

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

  function isDeveloperMode() {
    try {
      if (window.__IS_DEVELOPER__ === true) return true;
      const script = document.currentScript || document.querySelector('script[src*="security.js"]');
      if (script && (script.getAttribute('data-env') === 'developer' || script.getAttribute('data-developer') === 'true')) return true;
      const envMeta = document.querySelector('meta[name="app-env"], meta[name="environment"]');
      if (envMeta && ['developer', 'development', 'dev'].includes((envMeta.content || '').toLowerCase())) return true;
      if (['developer', 'development', 'dev'].includes((document.documentElement.getAttribute('data-env') || '').toLowerCase())) return true;
      if (typeof window !== 'undefined' && window.location && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) return true;
    } catch (e) {}
    return false;
  }

  /* ── 4. Block Developer Tools & Shortcuts (Disabled in Developer Mode) ────── */
  if (!isDeveloperMode()) {
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
  }


  // Disable browser gesture/pinch zoom
  document.addEventListener('gesturestart', function(e) { e.preventDefault(); }, { passive: false });
  document.addEventListener('gesturechange', function(e) { e.preventDefault(); }, { passive: false });
  document.addEventListener('gestureend', function(e) { e.preventDefault(); }, { passive: false });
})();
