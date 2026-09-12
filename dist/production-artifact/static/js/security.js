/**
 * AbhiHub Security Module
 * - Disables right-click context menu
 * - Blocks screenshot / screen-record keyboard shortcuts (PC & Mac)
 * - Detects mobile screenshot attempts via visibility / blur heuristics
 * - Shows a full-screen warning overlay on any violation
 * - Reports the incident to /api/report-suspect for audit logging
 */

(function () {
  'use strict';

  /* ── Warning Overlay ──────────────────────────────────────────────────── */
  let warningTimeout = null;

  function showWarning(message) {
    const overlay = document.getElementById('securityWarning');
    const msg = document.getElementById('securityWarningMsg');
    if (!overlay) return;

    if (msg) msg.textContent = message || '⚠️ Unauthorized action detected!';
    overlay.style.display = 'flex';
    overlay.classList.add('sec-warning-visible');

    clearTimeout(warningTimeout);
    warningTimeout = setTimeout(dismissWarning, 4000);
  }

  function dismissWarning() {
    const overlay = document.getElementById('securityWarning');
    if (overlay) {
      overlay.classList.remove('sec-warning-visible');
      setTimeout(() => { overlay.style.display = 'none'; }, 400);
    }
  }

  /* ── Suspect Reporting ────────────────────────────────────────────────── */
  function reportSuspect(action) {
    fetch('/api/report-suspect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ action })
    }).catch(() => {/* silent – network error shouldn't surface */});
  }

  /* ── Combined trigger ─────────────────────────────────────────────────── */
  function handleViolation(action, warningText) {
    reportSuspect(action);
    showWarning(warningText || '⚠️ ' + translateAction(action));
  }

  function translateAction(action) {
    const labels = {
      right_click:           'Right-click is disabled on this platform.',
      screenshot_key:        'Screenshot shortcut is not allowed.',
      printscreen_key:       'PrintScreen is not allowed.',
      screenrecord_key:      'Screen recording shortcut is not allowed.',
      devtools_key:          'DevTools shortcut is not allowed.',
      print_key:             'Printing is not allowed.',
      save_key:              'Saving is not allowed.',
      view_source_key:       'View Source is not allowed.',
      mobile_screenshot:     'Screenshot detected on this device.',
    };
    return labels[action] || 'This action is not allowed.';
  }

  /* ── 1. Disable Right-Click ───────────────────────────────────────────── */
  document.addEventListener('contextmenu', function (e) {
    e.preventDefault();
    handleViolation('right_click', '⚠️ Right-click is disabled on AbhiHub.');
  });

  /* ── 2. Block & Log Keyboard Shortcuts ────────────────────────────────── */
  document.addEventListener('keydown', function (e) {
    const key   = (e.key  || '').toLowerCase();
    const code  = (e.code || '');
    const ctrl  = e.ctrlKey  || e.metaKey; // treat Cmd (Mac) same as Ctrl
    const shift = e.shiftKey;
    const alt   = e.altKey;

    // PrintScreen
    if (code === 'PrintScreen' || key === 'printscreen') {
      e.preventDefault();
      handleViolation('printscreen_key');
      return;
    }

    // F12 – DevTools
    if (key === 'f12') {
      e.preventDefault();
      handleViolation('devtools_key');
      return;
    }

    // Ctrl/Cmd + Shift + I  (DevTools)
    if (ctrl && shift && (key === 'i' || key === 'j' || key === 'c' || key === 'k')) {
      e.preventDefault();
      handleViolation('devtools_key');
      return;
    }

    // Ctrl/Cmd + U  (View Source)
    if (ctrl && !shift && key === 'u') {
      e.preventDefault();
      handleViolation('view_source_key');
      return;
    }

    // Ctrl/Cmd + P  (Print – often used to PDF-screenshot)
    if (ctrl && !shift && key === 'p') {
      e.preventDefault();
      handleViolation('print_key');
      return;
    }

    // Ctrl/Cmd + S  (Save page)
    if (ctrl && !shift && key === 's') {
      e.preventDefault();
      handleViolation('save_key');
      return;
    }

    // Ctrl/Cmd + Shift + U  (Firefox view source alt)
    if (ctrl && shift && key === 'u') {
      e.preventDefault();
      handleViolation('view_source_key');
      return;
    }

    // macOS screenshot shortcuts: Cmd+Shift+3 / 4 / 5
    if (ctrl && shift && (key === '3' || key === '4' || key === '5')) {
      e.preventDefault();
      handleViolation('screenshot_key');
      return;
    }

    // Windows Game Bar / Xbox screenshot: Win+Alt+PrintScreen  (best-effort: Alt+PrintScreen)
    if (alt && (code === 'PrintScreen' || key === 'printscreen')) {
      e.preventDefault();
      handleViolation('screenshot_key');
      return;
    }

    // Windows Snipping Tool: Win+Shift+S is OS-level and untouchable, but
    // we block Ctrl+Shift+S as a partial deterrent
    if (ctrl && shift && key === 's') {
      e.preventDefault();
      handleViolation('screenrecord_key');
      return;
    }
  });

  /* ── 3. Mobile Screenshot Heuristic ──────────────────────────────────── */
  // When the user presses hardware buttons to screenshot, the browser page
  // briefly becomes hidden then visible again in rapid succession.
  let hiddenAt = 0;
  const SCREENSHOT_THRESHOLD_MS = 1200; // anything faster than 1.2 s is suspicious

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      hiddenAt = Date.now();
    } else {
      const elapsed = Date.now() - hiddenAt;
      if (hiddenAt > 0 && elapsed < SCREENSHOT_THRESHOLD_MS) {
        // Very quick hide+show → likely screenshot on mobile
        handleViolation('mobile_screenshot');
      }
      hiddenAt = 0;
    }
  });

  // Blur can fire when the OS screenshot overlay appears (esp. Android)
  let blurAt = 0;
  window.addEventListener('blur', function () { blurAt = Date.now(); });
  window.addEventListener('focus', function () {
    const elapsed = Date.now() - blurAt;
    if (blurAt > 0 && elapsed < SCREENSHOT_THRESHOLD_MS) {
      handleViolation('mobile_screenshot');
    }
    blurAt = 0;
  });

  /* ── 4. Close button on overlay ───────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    const btn = document.getElementById('securityWarningClose');
    if (btn) btn.addEventListener('click', dismissWarning);
  });

})();
