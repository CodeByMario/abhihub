/**
 * AbhiHub Engagement Layer — OverlayManager
 * Central orchestrator for all popups, gates, ads, and engagement prompts.
 *
 * Priority levels:
 *   100 — Critical Access Gates (auth, profile completion)
 *    80 — Core Engagement Gates (notifications, install)
 *    60 — Study Pass & Contribution prompts
 *    30 — Advertisements
 *    10 — Soft UX (toasts, chips)
 */

(function (global) {
  'use strict';

  const COOLDOWN_KEY_PREFIX = 'abhi_overlay_cd_';
  const DISMISS_COUNT_PREFIX = 'abhi_overlay_dc_';

  // ── Internal State ────────────────────────────────────────────────────────
  let _activeOverlay = null;   // currently visible blocking overlay id
  const _queue = [];           // sorted queue of pending overlays
  let _studyingMode = false;   // true while user is reading a paper

  // ── Helpers ───────────────────────────────────────────────────────────────

  function _now() { return Date.now(); }

  function _cdKey(id) { return COOLDOWN_KEY_PREFIX + id; }
  function _dcKey(id) { return DISMISS_COUNT_PREFIX + id; }

  function _getCooldown(id) {
    return parseInt(localStorage.getItem(_cdKey(id)) || '0', 10);
  }

  function _setCooldown(id, durationMs) {
    localStorage.setItem(_cdKey(id), String(_now() + durationMs));
  }

  function _getDismissCount(id) {
    return parseInt(localStorage.getItem(_dcKey(id)) || '0', 10);
  }

  function _incrementDismiss(id) {
    localStorage.setItem(_dcKey(id), String(_getDismissCount(id) + 1));
  }

  function _isCoolingDown(id) {
    return _now() < _getCooldown(id);
  }

  // ── Context Detection ─────────────────────────────────────────────────────

  /**
   * Call this when user enters paper-reading mode.
   * All non-critical overlays will be suppressed.
   */
  function enterStudyingMode() {
    _studyingMode = true;
    console.log('[OverlayManager] Studying mode: ON');
  }

  /**
   * Call this when user leaves paper-reading mode.
   */
  function exitStudyingMode() {
    _studyingMode = false;
    console.log('[OverlayManager] Studying mode: OFF');
    _processQueue();
  }

  // ── Queue ─────────────────────────────────────────────────────────────────

  function _enqueue(overlay) {
    // Remove duplicate if already queued
    const idx = _queue.findIndex(o => o.id === overlay.id);
    if (idx !== -1) _queue.splice(idx, 1);

    _queue.push(overlay);
    _queue.sort((a, b) => b.priority - a.priority); // highest priority first
  }

  function _processQueue() {
    if (_activeOverlay) return; // something already showing
    if (_queue.length === 0) return;

    const next = _queue[0];

    // Suppress non-critical overlays during studying
    if (_studyingMode && next.priority < 100) {
      console.log('[OverlayManager] Suppressed during studying mode:', next.id);
      return;
    }

    // Check cooldown
    if (_isCoolingDown(next.id)) {
      // Skip this one and try next lower priority
      const cooled = _queue.filter(o => !_isCoolingDown(o.id));
      if (!cooled.length) return;
      const fallback = cooled[0];
      if (_studyingMode && fallback.priority < 100) return;
      _showOverlay(fallback);
      return;
    }

    _showOverlay(next);
  }

  function _showOverlay(overlay) {
    const idx = _queue.indexOf(overlay);
    if (idx !== -1) _queue.splice(idx, 1);

    _activeOverlay = overlay.id;
    console.log('[OverlayManager] Showing:', overlay.id, '(priority', overlay.priority + ')');

    try {
      overlay.show();
    } catch (e) {
      console.error('[OverlayManager] Error showing overlay:', overlay.id, e);
      _activeOverlay = null;
      _processQueue();
    }
  }

  // ── Public API ────────────────────────────────────────────────────────────

  /**
   * Register and enqueue an overlay.
   *
   * @param {Object} config
   * @param {string}   config.id          Unique identifier
   * @param {number}   config.priority     100=critical … 10=soft
   * @param {Function} config.show         Called to render the overlay
   * @param {number}   [config.cooldownMs] Minimum ms between shows (default 0)
   * @param {number}   [config.maxDismiss] Max dismissals before enforcement
   * @param {boolean}  [config.immediate]  Skip queue and show now if possible
   */
  function request(config) {
    if (!config || !config.id || typeof config.show !== 'function') {
      console.warn('[OverlayManager] Invalid overlay config:', config);
      return;
    }

    // Respect cooldown unless priority is critical (100)
    if (config.priority < 100 && _isCoolingDown(config.id)) {
      console.log('[OverlayManager] Cooldown active, skipping:', config.id);
      return;
    }

    _enqueue(config);

    if (config.immediate && !_activeOverlay) {
      _processQueue();
    } else {
      setTimeout(_processQueue, 200); // slight delay to avoid race on page load
    }
  }

  /**
   * Must be called by overlay's dismiss/close handler.
   * @param {string} id
   * @param {number} [cooldownMs] Cooldown before this overlay can show again
   */
  function dismiss(id, cooldownMs) {
    if (_activeOverlay === id) {
      _activeOverlay = null;
    }
    _incrementDismiss(id);
    if (cooldownMs) _setCooldown(id, cooldownMs);
    setTimeout(_processQueue, 300);
  }

  /**
   * Mark an overlay as permanently completed (won't show again).
   */
  function complete(id) {
    localStorage.setItem(_cdKey(id), String(Number.MAX_SAFE_INTEGER));
    if (_activeOverlay === id) _activeOverlay = null;
    setTimeout(_processQueue, 300);
  }

  /**
   * Returns true if there is currently a blocking overlay visible.
   */
  function isBlocking() {
    return _activeOverlay !== null;
  }

  /**
   * Get dismiss count for an overlay id.
   */
  function getDismissCount(id) {
    return _getDismissCount(id);
  }

  // ── Expose ────────────────────────────────────────────────────────────────

  global.OverlayManager = {
    request,
    dismiss,
    complete,
    isBlocking,
    getDismissCount,
    enterStudyingMode,
    exitStudyingMode
  };

  console.log('[OverlayManager] Initialized.');

})(window);
