/**
 * AbhiHub Access Gates
 * Manages mandatory onboarding gates: Profile Completion & Notifications.
 * Integrates with OverlayManager for safe, conflict-free display.
 *
 * Depends on: overlay-manager.js, push-notifications.js
 */

(function (global) {
  'use strict';

  const PROFILE_DONE_KEY   = 'abhi_profile_completed';
  const NOTIF_DONE_KEY     = 'abhi_notif_done';
  const NOTIF_BLOCKED_KEY  = 'abhi_notif_blocked';

  const NOTIF_COOLDOWN_MS  = 24 * 60 * 60 * 1000; // 24 h
  const NOTIF_MAX_DISMISS  = 3;                     // enforce after 3 dismissals

  // ── Profile Completion Gate ───────────────────────────────────────────────

  function checkProfileGate() {
    if (localStorage.getItem(PROFILE_DONE_KEY) === '1') return;

    // Delegate to existing server-side profile check if available
    fetch('/api/profile-status', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        if (data.profile_completed) {
          localStorage.setItem(PROFILE_DONE_KEY, '1');
          return;
        }
        _requestProfileGate();
      })
      .catch(() => {
        // Silently ignore — don't block the user if endpoint is unavailable
      });
  }

  function _requestProfileGate() {
    if (!window.OverlayManager) return;

    window.OverlayManager.request({
      id: 'profile-completion-gate',
      priority: 100,
      immediate: true,
      show: _showProfileModal
    });
  }

  function _showProfileModal() {
    const existing = document.getElementById('accessGateProfileModal');
    if (existing) { existing.style.display = 'flex'; return; }

    const modal = document.createElement('div');
    modal.id = 'accessGateProfileModal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'agProfileTitle');
    modal.style.cssText = [
      'position:fixed;inset:0;z-index:9000',
      'display:flex;align-items:center;justify-content:center',
      'background:rgba(15,23,42,0.65);backdrop-filter:blur(4px)',
      'padding:1rem'
    ].join(';');

    modal.innerHTML = `
      <div class="ag-card" style="
        background:#fff;border-radius:20px;padding:2rem;max-width:420px;width:100%;
        box-shadow:0 24px 64px rgba(0,0,0,0.22);text-align:center;
        animation:agSlideUp .35s cubic-bezier(.22,1,.36,1) both;
      ">
        <div style="font-size:3rem;margin-bottom:.75rem;">📚</div>
        <h2 id="agProfileTitle" style="font-size:1.4rem;font-weight:700;color:#1e293b;margin-bottom:.5rem;">
          Complete your study profile
        </h2>
        <p style="color:#64748b;font-size:.95rem;line-height:1.55;margin-bottom:1.5rem;">
          Adding your branch and semester helps AbhiHub recommend the most relevant papers and notes for you.
        </p>
        <a href="/account" id="agProfileCTA"
           style="display:block;width:100%;padding:.85rem;background:linear-gradient(135deg,#2563eb,#1d4ed8);
                  color:#fff;border-radius:12px;font-weight:700;font-size:1rem;text-decoration:none;
                  margin-bottom:.6rem;box-shadow:0 4px 16px rgba(37,99,235,.28);"
           onclick="window.AccessGates.dismissProfile(false);">
          Complete Profile
        </a>
        <button onclick="window.AccessGates.dismissProfile(true)"
                style="background:none;border:none;color:#94a3b8;font-size:.88rem;cursor:pointer;padding:.3rem;">
          Skip for Now
        </button>
      </div>`;

    document.body.appendChild(modal);
    modal.addEventListener('click', e => {
      if (e.target === modal) window.AccessGates.dismissProfile(true);
    });
  }

  function dismissProfile(skipped) {
    const modal = document.getElementById('accessGateProfileModal');
    if (modal) modal.style.display = 'none';

    if (!skipped) {
      localStorage.setItem(PROFILE_DONE_KEY, '1');
      window.OverlayManager && window.OverlayManager.complete('profile-completion-gate');
    } else {
      // Skipped: cooldown 6 h, will re-prompt
      window.OverlayManager && window.OverlayManager.dismiss('profile-completion-gate', 6 * 60 * 60 * 1000);
    }
  }

  // ── Notification Engagement Gate ──────────────────────────────────────────

  function checkNotificationGate() {
    if (localStorage.getItem(NOTIF_DONE_KEY)    === '1') return;
    if (localStorage.getItem(NOTIF_BLOCKED_KEY) === '1') return;

    // Don't push if browser doesn't support
    if (!('Notification' in window)) {
      localStorage.setItem(NOTIF_DONE_KEY, '1');
      return;
    }

    if (Notification.permission === 'granted') {
      localStorage.setItem(NOTIF_DONE_KEY, '1');
      return;
    }

    if (!window.OverlayManager) return;

    window.OverlayManager.request({
      id: 'notification-gate',
      priority: 80,
      cooldownMs: NOTIF_COOLDOWN_MS,
      maxDismiss: NOTIF_MAX_DISMISS,
      show: _showNotifModal
    });
  }

  function _showNotifModal() {
    const existing = document.getElementById('accessGateNotifModal');
    if (existing) { existing.style.display = 'flex'; return; }

    const dismissCount = window.OverlayManager
      ? window.OverlayManager.getDismissCount('notification-gate')
      : 0;

    const isEnforced = dismissCount >= NOTIF_MAX_DISMISS;

    const modal = document.createElement('div');
    modal.id = 'accessGateNotifModal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'agNotifTitle');
    modal.style.cssText = [
      'position:fixed;inset:0;z-index:8900',
      'display:flex;align-items:center;justify-content:center',
      'background:rgba(15,23,42,0.65);backdrop-filter:blur(4px)',
      'padding:1rem'
    ].join(';');

    modal.innerHTML = `
      <div class="ag-card" style="
        background:#fff;border-radius:20px;padding:2rem;max-width:400px;width:100%;
        box-shadow:0 24px 64px rgba(0,0,0,0.22);text-align:center;
        animation:agSlideUp .35s cubic-bezier(.22,1,.36,1) both;
      ">
        <div style="font-size:3rem;margin-bottom:.75rem;">🔔</div>
        <h2 id="agNotifTitle" style="font-size:1.35rem;font-weight:700;color:#1e293b;margin-bottom:.5rem;">
          Stay exam-ready 🔔
        </h2>
        <p style="color:#64748b;font-size:.92rem;line-height:1.55;margin-bottom:1.4rem;">
          Enable notifications to get important updates, new papers, and exam alerts instantly.
        </p>
        <button id="agNotifEnableBtn" onclick="window.AccessGates.enableNotifications()"
                style="display:block;width:100%;padding:.85rem;border:none;border-radius:12px;
                       background:linear-gradient(135deg,#0891b2,#2563eb);color:#fff;
                       font-size:1rem;font-weight:700;cursor:pointer;margin-bottom:.6rem;
                       box-shadow:0 4px 18px rgba(8,145,178,.28);">
          Enable Notifications
        </button>
        ${!isEnforced ? `
        <button onclick="window.AccessGates.dismissNotif()"
                style="background:none;border:none;color:#94a3b8;font-size:.88rem;cursor:pointer;padding:.3rem;">
          Maybe Later
        </button>` : `
        <p style="font-size:.8rem;color:#f59e0b;margin-top:.4rem;">
          ⚠️ Please enable to continue using all features.
        </p>`}
      </div>`;

    document.body.appendChild(modal);

    // If not enforced, allow backdrop dismiss
    if (!isEnforced) {
      modal.addEventListener('click', e => {
        if (e.target === modal) window.AccessGates.dismissNotif();
      });
    }
  }

  async function enableNotifications() {
    const btn = document.getElementById('agNotifEnableBtn');
    if (btn) btn.textContent = 'Enabling…';

    try {
      if (window.PushNotifications && window.PushNotifications.isSupported()) {
        const result = await window.PushNotifications.subscribe();
        if (result && result.success) {
          if (btn) btn.textContent = '✅ Enabled!';
          localStorage.setItem(NOTIF_DONE_KEY, '1');
          setTimeout(() => {
            const m = document.getElementById('accessGateNotifModal');
            if (m) m.style.display = 'none';
            window.OverlayManager && window.OverlayManager.complete('notification-gate');
          }, 1000);
          return;
        }
      }
      // Fallback — browser native
      const perm = await Notification.requestPermission();
      if (perm === 'granted') {
        localStorage.setItem(NOTIF_DONE_KEY, '1');
        if (btn) btn.textContent = '✅ Enabled!';
        setTimeout(() => {
          const m = document.getElementById('accessGateNotifModal');
          if (m) m.style.display = 'none';
          window.OverlayManager && window.OverlayManager.complete('notification-gate');
        }, 900);
      } else if (perm === 'denied') {
        localStorage.setItem(NOTIF_BLOCKED_KEY, '1');
        dismissNotif();
      } else {
        if (btn) btn.textContent = 'Enable Notifications';
      }
    } catch (e) {
      console.error('[AccessGates] Notification enable error:', e);
      if (btn) btn.textContent = 'Enable Notifications';
    }
  }

  function dismissNotif() {
    const modal = document.getElementById('accessGateNotifModal');
    if (modal) modal.style.display = 'none';
    // 24 h cooldown
    window.OverlayManager && window.OverlayManager.dismiss('notification-gate', NOTIF_COOLDOWN_MS);
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  function init() {
    // Delay checks to avoid interfering with page load
    setTimeout(() => {
      checkProfileGate();
      setTimeout(checkNotificationGate, 2000);
    }, 1500);
  }

  // ── Expose ────────────────────────────────────────────────────────────────

  global.AccessGates = {
    init,
    checkProfileGate,
    checkNotificationGate,
    dismissProfile,
    enableNotifications,
    dismissNotif
  };

})(window);
