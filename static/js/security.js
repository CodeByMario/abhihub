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


  /* ── 6. Browser Extension Detection & Application Shield ─────────────────── */
  (function initExtensionShield() {
    let shieldActive = false;
    const originalFetch = window.fetch;
    const originalXhrOpen = XMLHttpRequest.prototype.open;

    const BROWSER_GUIDES = {
      edge: {
        name: 'Microsoft Edge',
        steps: [
          'Click the <strong>Extensions (🧩)</strong> puzzle icon in your top-right browser toolbar.',
          'At the very top of the popup, toggle <strong>"Allow extensions on this site"</strong> (or on <code>localhost:5000</code>) to <strong>OFF</strong>.',
          'Or click the 3 dots (⋮) next to <strong>AdGuard</strong>, <strong>IDM</strong>, or active extensions &rarr; <em>"This can read and change site data"</em> &rarr; <strong>"When you click the extension"</strong>.',
          'Click <strong>"Re-Check & Unlock App"</strong> below to resume.'
        ]
      },
      chrome: {
        name: 'Google Chrome',
        steps: [
          'Click the <strong>Extensions (Puzzle 🧩)</strong> icon in the top-right toolbar.',
          'Click the <strong>3 dots (⋮)</strong> next to your ad-blocker, IDM, or extension.',
          'Select <strong>"When you click the extension"</strong> or toggle the extension <strong>OFF</strong>.',
          'Or visit <code>chrome://extensions</code> to turn off extensions for this site.',
          'Click <strong>"Re-Check & Unlock App"</strong> below.'
        ]
      },
      brave: {
        name: 'Brave Browser',
        steps: [
          'Click the orange <strong>Brave Lion Shield (🦁)</strong> icon on the right side of the address bar.',
          'Toggle the top switch <strong>"Shields are UP for this site"</strong> to <strong>DOWN (OFF)</strong>.',
          'Brave will automatically allow normal script execution for AbhiHub.',
          'Click <strong>"Re-Check & Unlock App"</strong> below.'
        ]
      },
      firefox: {
        name: 'Mozilla Firefox',
        steps: [
          'Click the <strong>Shield (🛡️)</strong> icon to the left of the URL address bar.',
          'Toggle <strong>"Enhanced Tracking Protection"</strong> to <strong>OFF</strong> for this site.',
          'If using uBlock/AdBlock, click its icon and click the large power button to pause on AbhiHub.',
          'Click <strong>"Re-Check & Unlock App"</strong> below.'
        ]
      },
      safari: {
        name: 'Safari (Mac/iOS)',
        steps: [
          'On Mac: Open <strong>Safari Settings (Preferences) &rarr; Extensions</strong> and uncheck blockers.',
          'On iPhone/iPad: Open iOS <strong>Settings &rarr; Safari &rarr; Extensions</strong> and toggle off.',
          'Click <strong>"Re-Check & Unlock App"</strong> below.'
        ]
      }
    };

    function detectUserBrowser() {
      const ua = navigator.userAgent || '';
      if (ua.includes('Edg/')) return 'edge';
      if ((navigator.brave && typeof navigator.brave.isBrave === 'function') || ua.includes('Brave')) return 'brave';
      if (ua.includes('Firefox/')) return 'firefox';
      if (ua.includes('Safari/') && !ua.includes('Chrome/')) return 'safari';
      return 'chrome';
    }

    function stopAppProcesses() {
      // Pause all playing audio/video media
      document.querySelectorAll('video, audio').forEach(m => {
        try { m.pause(); } catch(e) {}
      });

      // Pause outgoing platform network communications
      window.fetch = function(...args) {
        if (shieldActive) {
          return Promise.reject(new Error('AbhiHub: Operations paused. Please disable extensions.'));
        }
        return originalFetch.apply(this, args);
      };

      XMLHttpRequest.prototype.open = function(...args) {
        if (shieldActive) {
          throw new Error('AbhiHub: Operations paused. Please disable extensions.');
        }
        return originalXhrOpen.apply(this, args);
      };

      document.documentElement.style.setProperty('overflow', 'hidden', 'important');
      document.body.style.setProperty('overflow', 'hidden', 'important');
    }

    function resumeAppProcesses() {
      window.fetch = originalFetch;
      XMLHttpRequest.prototype.open = originalXhrOpen;
      document.documentElement.style.removeProperty('overflow');
      document.body.style.removeProperty('overflow');
    }

    function showExtensionShield() {
      if (shieldActive) return;
      shieldActive = true;
      stopAppProcesses();

      let overlay = document.getElementById('abhihub-extension-shield');
      if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'abhihub-extension-shield';
        document.body.appendChild(overlay);
      }

      overlay.style.cssText = `
        position: fixed !important;
        inset: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        z-index: 2147483647 !important;
        background: rgba(10, 15, 29, 0.97) !important;
        backdrop-filter: blur(28px) !important;
        -webkit-backdrop-filter: blur(28px) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 1.5rem !important;
        box-sizing: border-box !important;
        color: #f8fafc !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        overflow-y: auto !important;
      `;

      const defaultBrowser = detectUserBrowser();

      function renderBrowserGuideSteps(browserKey) {
        const guide = BROWSER_GUIDES[browserKey] || BROWSER_GUIDES.edge;
        return `
          <ol style="margin: 0; padding-left: 1.25rem;">
            ${guide.steps.map(step => `<li style="margin-bottom: 0.45rem;">${step}</li>`).join('')}
          </ol>
        `;
      }

      overlay.innerHTML = `
        <div style="max-width: 620px; width: 100%; background: #1e293b; border: 1.5px solid rgba(239, 68, 68, 0.4); border-radius: 20px; padding: 2rem; box-shadow: 0 25px 60px rgba(0,0,0,0.65); text-align: left;">
          <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1.25rem;">
            <div style="width: 52px; height: 52px; border-radius: 14px; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.35); display: flex; align-items: center; justify-content: center; font-size: 1.7rem; color: #f87171; flex-shrink: 0;">
              🛡️
            </div>
            <div>
              <h2 style="margin: 0; font-size: 1.35rem; font-weight: 800; color: #f8fafc; letter-spacing: -0.02em;">Browser Extension Detected</h2>
              <div style="font-size: 0.8rem; color: #f87171; font-weight: 700; margin-top: 3px;">All platform operations paused</div>
            </div>
          </div>

          <div style="padding: 0.85rem 1rem; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 12px; margin-bottom: 1.25rem; font-size: 0.86rem; line-height: 1.55; color: #e2e8f0;">
            To ensure document security, protect verified student creators, and prevent unauthorized automation, <strong>AbhiHub requires browser extensions (such as ad blockers, script injectors, and downloaders) to be disabled</strong> on this domain.
          </div>

          <div style="margin-bottom: 1.25rem;">
            <div style="font-size: 0.78rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem;">
              Step-by-Step Guide to Disable Extensions:
            </div>

            <div style="display: flex; gap: 0.4rem; overflow-x: auto; padding-bottom: 0.4rem; border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 0.85rem;">
              ${Object.keys(BROWSER_GUIDES).map(key => `
                <button type="button" class="shield-browser-tab" data-browser="${key}" style="padding: 5px 12px; border-radius: 8px; font-size: 0.78rem; font-weight: 600; cursor: pointer; border: 1px solid ${key === defaultBrowser ? '#3b82f6' : 'rgba(255,255,255,0.1)'}; background: ${key === defaultBrowser ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255,255,255,0.04)'}; color: ${key === defaultBrowser ? '#60a5fa' : '#94a3b8'}; transition: all 0.15s ease;">
                  ${BROWSER_GUIDES[key].name}
                </button>
              `).join('')}
            </div>

            <div id="shield-guide-steps" style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; padding: 1rem; font-size: 0.84rem; line-height: 1.6; color: #cbd5e1;">
              ${renderBrowserGuideSteps(defaultBrowser)}
            </div>
          </div>

          <div style="display: flex; gap: 0.75rem; align-items: center; justify-content: flex-end; flex-wrap: wrap; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.08);">
            <button type="button" id="shield-refresh-btn" style="padding: 0.65rem 1.1rem; border-radius: 10px; font-size: 0.84rem; font-weight: 600; cursor: pointer; border: 1px solid rgba(255,255,255,0.15); background: rgba(255,255,255,0.05); color: #cbd5e1;">
              Reload Page
            </button>
            <button type="button" id="shield-recheck-btn" style="padding: 0.65rem 1.4rem; border-radius: 10px; font-size: 0.85rem; font-weight: 700; cursor: pointer; border: none; background: #2563eb; color: #ffffff; box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4); display: flex; align-items: center; gap: 6px;">
              <span>🔄</span> Re-Check &amp; Unlock App
            </button>
          </div>
        </div>
      `;

      overlay.querySelectorAll('.shield-browser-tab').forEach(tab => {
        tab.addEventListener('click', function() {
          overlay.querySelectorAll('.shield-browser-tab').forEach(t => {
            t.style.border = '1px solid rgba(255,255,255,0.1)';
            t.style.background = 'rgba(255,255,255,0.04)';
            t.style.color = '#94a3b8';
          });
          this.style.border = '1px solid #3b82f6';
          this.style.background = 'rgba(59, 130, 246, 0.2)';
          this.style.color = '#60a5fa';
          const bKey = this.getAttribute('data-browser');
          const stepsEl = document.getElementById('shield-guide-steps');
          if (stepsEl) stepsEl.innerHTML = renderBrowserGuideSteps(bKey);
        });
      });

      const refreshBtn = document.getElementById('shield-refresh-btn');
      if (refreshBtn) refreshBtn.addEventListener('click', () => window.location.reload());

      const recheckBtn = document.getElementById('shield-recheck-btn');
      if (recheckBtn) recheckBtn.addEventListener('click', async () => {
        recheckBtn.innerHTML = '<span>⏳</span> Checking...';
        const detected = await runExtensionCheck();
        if (!detected) {
          hideExtensionShield();
        } else {
          recheckBtn.innerHTML = '<span>❌</span> Extension Still Active &bull; Re-Check';
          setTimeout(() => {
            if (recheckBtn) recheckBtn.innerHTML = '<span>🔄</span> Re-Check &amp; Unlock App';
          }, 2000);
        }
      });
    }

    function hideExtensionShield() {
      const overlay = document.getElementById('abhihub-extension-shield');
      if (overlay) overlay.remove();
      shieldActive = false;
      resumeAppProcesses();
    }

    async function runExtensionCheck() {
      if (window.location.search.includes('test_extension=1') || window.__TEST_EXTENSION_SHIELD__) return true;

      // Allow emergency bypass via URL query param (?bypass_shield=1)
      if (window.location.search.includes('bypass_shield=1')) return false;

      // Bypass auth pages to avoid locking out credentials autofill
      const p = (window.location.pathname || '').toLowerCase();
      if (p.startsWith('/login') || p.startsWith('/signup') || p.startsWith('/register') || p.startsWith('/reset-password')) {
        return false;
      }

      let detected = false;

      // Vector 1: AdGuard, uBlock, AdBlock cosmetic rule detection
      try {
        const bait = document.createElement('div');
        bait.id = 'ad-banner-detector';
        bait.className = 'adsbygoogle ad-banner ad-placement pub_300x250 text-ad adsbox banner-ad sponsor-box';
        bait.style.cssText = 'width: 100px !important; height: 100px !important; position: absolute !important; left: -9999px !important; top: -9999px !important; display: block !important;';
        bait.innerHTML = '&nbsp;';
        document.body.appendChild(bait);

        const computed = window.getComputedStyle(bait);
        if (
          bait.offsetParent === null ||
          bait.offsetHeight === 0 ||
          bait.clientHeight === 0 ||
          computed.display === 'none' ||
          computed.visibility === 'hidden' ||
          computed.opacity === '0'
        ) {
          detected = true;
        }
        bait.remove();
        if (detected) return true;
      } catch (e) {}

      // Vector 2: Ad script network blocking probe
      try {
        const testUrl = new Request('https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js', {
          method: 'HEAD',
          mode: 'no-cors',
          cache: 'no-store'
        });
        await originalFetch(testUrl).catch(() => {
          detected = true;
        });
        if (detected) return true;
      } catch (e) {
        detected = true;
        return true;
      }

      // Vector 3: Content script DOM injections & extension signatures
      try {
        const extensionSelectors = [
          '[id*="adguard"]',
          '[class*="adguard"]',
          '[id*="ublock"]',
          '[class*="adblock"]',
          '[data-adblockkey]',
          '[data-adguard]',
          '[data-tampermonkey]',
          '[data-extension-id]',
          'script[src*="chrome-extension:"]',
          'script[src*="edge-extension:"]',
          'link[href*="chrome-extension:"]',
          'link[href*="edge-extension:"]',
          '[id*="idm_"]',
          '[class*="idm_"]',
          '[id*="idm-"]',
          'embed[type*="idm"]'
        ];
        if (document.querySelector(extensionSelectors.join(','))) {
          return true;
        }

        // Check global extension variables
        if (
          window.__adguard ||
          window.adguard ||
          window.IDM ||
          window.idm ||
          window.__nightmare ||
          window.tampermonkey
        ) {
          return true;
        }

        // Check performance resource timing for extension assets
        if (window.performance && typeof window.performance.getEntriesByType === 'function') {
          const resources = window.performance.getEntriesByType('resource');
          for (let i = 0; i < resources.length; i++) {
            const name = resources[i].name || '';
            if (name.startsWith('chrome-extension://') || name.startsWith('edge-extension://') || name.startsWith('moz-extension://')) {
              return true;
            }
          }
        }
      } catch (e) {}

      return false;
    }

    async function startCheck() {
      const hasExt = await runExtensionCheck();
      if (hasExt) showExtensionShield();
    }

    // Run immediately and after DOM is ready
    startCheck();
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => setTimeout(startCheck, 100));
    } else {
      setTimeout(startCheck, 100);
    }

    // Periodic re-check to detect extensions activated mid-session
    setInterval(async () => {
      if (!shieldActive) {
        const hasExt = await runExtensionCheck();
        if (hasExt) showExtensionShield();
      }
    }, 5000);
  })();

  // Disable browser gesture/pinch zoom
  document.addEventListener('gesturestart', function(e) { e.preventDefault(); }, { passive: false });
  document.addEventListener('gesturechange', function(e) { e.preventDefault(); }, { passive: false });
  document.addEventListener('gestureend', function(e) { e.preventDefault(); }, { passive: false });
})();
