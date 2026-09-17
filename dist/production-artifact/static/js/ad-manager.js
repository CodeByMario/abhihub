/**
 * AbhiHub Ad Manager
 * Safe advertisement scheduling that respects study flow and OverlayManager rules.
 *
 * Ad types:
 *   - Inline Cards  (priority 10, rendered in DOM, never blocking)
 *   - Interstitial  (priority 30, full-screen, max once/session, not during study)
 *   - Rewarded      (priority 40, optional, offers bonus views)
 *
 * Depends on: overlay-manager.js
 */

(function (global) {
  'use strict';

  const SESSION_INTERSTITIAL_KEY = 'abhi_ad_interstitial_shown';
  const INTERSTITIAL_COOLDOWN_MS = 30 * 60 * 1000; // 30 min between sessions

  // Active ad registry (for inline cards)
  const _inlineSlots = {};

  // ── Inline Card Ads ───────────────────────────────────────────────────────

  /**
   * Render an inline ad card into a container element.
   * These are non-blocking and respect priority 10.
   *
   * @param {string} slotId   - DOM id of the target container
   * @param {Object} adConfig - { title, body, ctaText, ctaUrl, imageUrl? }
   */
  function renderInlineAd(slotId, adConfig) {
    const slot = document.getElementById(slotId);
    if (!slot || !adConfig) return;

    // Don't show if studying
    if (window.OverlayManager && window.OverlayManager.isBlocking()) return;

    slot.innerHTML = `
      <div class="ad-inline-card" role="complementary" aria-label="Advertisement">
        <span class="ad-label">Ad</span>
        ${adConfig.imageUrl ? `<img src="${adConfig.imageUrl}" alt="" class="ad-inline-img" loading="lazy">` : ''}
        <div class="ad-inline-body">
          <div class="ad-inline-title">${adConfig.title || ''}</div>
          <div class="ad-inline-text">${adConfig.body || ''}</div>
          ${adConfig.ctaUrl ? `
            <a href="${adConfig.ctaUrl}" target="_blank" rel="noopener noreferrer"
               class="ad-inline-cta" onclick="AdManager.trackClick('inline','${slotId}')">
              ${adConfig.ctaText || 'Learn More'}
            </a>` : ''}
        </div>
        <button class="ad-dismiss-btn" onclick="AdManager.dismissInline('${slotId}')"
                aria-label="Close ad">✕</button>
      </div>`;

    _inlineSlots[slotId] = adConfig;
  }

  function dismissInline(slotId) {
    const slot = document.getElementById(slotId);
    if (slot) slot.innerHTML = '';
    delete _inlineSlots[slotId];
  }

  // ── Interstitial Ad ───────────────────────────────────────────────────────

  /**
   * Request an interstitial ad popup (max once per session, never during study).
   *
   * @param {Object} adConfig - { title, body, ctaText, ctaUrl, imageUrl? }
   */
  function requestInterstitial(adConfig) {
    if (!window.OverlayManager) return;

    // Max once per session
    if (sessionStorage.getItem(SESSION_INTERSTITIAL_KEY) === '1') return;

    window.OverlayManager.request({
      id: 'ad-interstitial',
      priority: 30,
      cooldownMs: INTERSTITIAL_COOLDOWN_MS,
      show: () => _showInterstitial(adConfig)
    });
  }

  function _showInterstitial(adConfig) {
    sessionStorage.setItem(SESSION_INTERSTITIAL_KEY, '1');

    const existing = document.getElementById('adInterstitialOverlay');
    if (existing) { existing.style.display = 'flex'; return; }

    const overlay = document.createElement('div');
    overlay.id = 'adInterstitialOverlay';
    overlay.style.cssText = [
      'position:fixed;inset:0;z-index:8000',
      'display:flex;align-items:center;justify-content:center',
      'background:rgba(15,23,42,0.7);backdrop-filter:blur(4px)',
      'padding:1rem'
    ].join(';');

    overlay.innerHTML = `
      <div class="ag-card" style="
        background:#fff;border-radius:20px;padding:2rem;max-width:420px;width:100%;
        box-shadow:0 24px 64px rgba(0,0,0,0.22);text-align:center;
        animation:agSlideUp .35s cubic-bezier(.22,1,.36,1) both;position:relative;
      ">
        <span class="ad-label" style="position:absolute;top:1rem;left:1rem;">Ad</span>
        <button onclick="AdManager.dismissInterstitial()"
                style="position:absolute;top:.8rem;right:.8rem;background:#f1f5f9;
                       border:none;border-radius:50%;width:32px;height:32px;cursor:pointer;
                       font-size:1rem;color:#64748b;display:flex;align-items:center;justify-content:center;"
                aria-label="Close ad">✕</button>
        ${adConfig.imageUrl ? `<img src="${adConfig.imageUrl}" alt="" style="width:100%;border-radius:12px;margin-bottom:1rem;max-height:180px;object-fit:cover;" loading="lazy">` : ''}
        <h3 style="font-size:1.2rem;font-weight:700;color:#1e293b;margin-bottom:.5rem;">${adConfig.title || ''}</h3>
        <p style="color:#64748b;font-size:.9rem;line-height:1.5;margin-bottom:1.2rem;">${adConfig.body || ''}</p>
        ${adConfig.ctaUrl ? `
          <a href="${adConfig.ctaUrl}" target="_blank" rel="noopener noreferrer"
             style="display:block;padding:.8rem;background:linear-gradient(135deg,#2563eb,#1d4ed8);
                    color:#fff;border-radius:12px;font-weight:700;text-decoration:none;margin-bottom:.5rem;"
             onclick="AdManager.trackClick('interstitial','')">
            ${adConfig.ctaText || 'Learn More'}
          </a>` : ''}
        <button onclick="AdManager.dismissInterstitial()"
                style="background:none;border:none;color:#94a3b8;font-size:.85rem;cursor:pointer;">
          No Thanks
        </button>
      </div>`;

    document.body.appendChild(overlay);
    overlay.addEventListener('click', e => {
      if (e.target === overlay) AdManager.dismissInterstitial();
    });
  }

  function dismissInterstitial() {
    const overlay = document.getElementById('adInterstitialOverlay');
    if (overlay) overlay.style.display = 'none';
    window.OverlayManager && window.OverlayManager.dismiss('ad-interstitial', INTERSTITIAL_COOLDOWN_MS);
  }

  // ── Rewarded Ad ───────────────────────────────────────────────────────────

  /**
   * Show an optional rewarded prompt offering bonus views or reputation.
   * Never mandatory.
   *
   * @param {Object} config - { rewardLabel, onAccept, onDecline }
   */
  function requestRewarded(config) {
    if (!window.OverlayManager) return;

    window.OverlayManager.request({
      id: 'ad-rewarded',
      priority: 40,
      cooldownMs: 4 * 60 * 60 * 1000, // 4 h
      show: () => _showRewarded(config)
    });
  }

  function _showRewarded(config) {
    const overlay = document.createElement('div');
    overlay.id = 'adRewardedOverlay';
    overlay.style.cssText = [
      'position:fixed;inset:0;z-index:8100',
      'display:flex;align-items:center;justify-content:center',
      'background:rgba(15,23,42,0.65);backdrop-filter:blur(4px)',
      'padding:1rem'
    ].join(';');

    overlay.innerHTML = `
      <div class="ag-card" style="
        background:#fff;border-radius:20px;padding:2rem;max-width:380px;width:100%;
        box-shadow:0 24px 64px rgba(0,0,0,0.22);text-align:center;
        animation:agSlideUp .35s cubic-bezier(.22,1,.36,1) both;
      ">
        <div style="font-size:2.5rem;margin-bottom:.75rem;">🎁</div>
        <h3 style="font-size:1.2rem;font-weight:700;color:#1e293b;margin-bottom:.5rem;">Bonus offer!</h3>
        <p style="color:#64748b;font-size:.92rem;line-height:1.5;margin-bottom:1.3rem;">
          ${config.rewardLabel || 'Watch a short message and earn bonus views!'}
        </p>
        <button onclick="AdManager._acceptRewarded()"
                style="display:block;width:100%;padding:.85rem;border:none;border-radius:12px;
                       background:linear-gradient(135deg,#10b981,#059669);color:#fff;
                       font-weight:700;font-size:1rem;cursor:pointer;margin-bottom:.6rem;">
          Claim Bonus 🎉
        </button>
        <button onclick="AdManager._declineRewarded()"
                style="background:none;border:none;color:#94a3b8;font-size:.88rem;cursor:pointer;">
          Not Now
        </button>
      </div>`;

    document.body.appendChild(overlay);
    overlay._config = config;
  }

  function _acceptRewarded() {
    const overlay = document.getElementById('adRewardedOverlay');
    if (overlay && overlay._config && typeof overlay._config.onAccept === 'function') {
      overlay._config.onAccept();
    }
    if (overlay) overlay.remove();
    window.OverlayManager && window.OverlayManager.complete('ad-rewarded');
    trackClick('rewarded', 'accept');
  }

  function _declineRewarded() {
    const overlay = document.getElementById('adRewardedOverlay');
    if (overlay && overlay._config && typeof overlay._config.onDecline === 'function') {
      overlay._config.onDecline();
    }
    if (overlay) overlay.remove();
    window.OverlayManager && window.OverlayManager.dismiss('ad-rewarded', 4 * 60 * 60 * 1000);
    trackClick('rewarded', 'decline');
  }

  // ── Analytics ─────────────────────────────────────────────────────────────

  function trackClick(type, slotId) {
    try {
      if (window.AbhiHubTracking && typeof window.AbhiHubTracking.trackEvent === 'function') {
        window.AbhiHubTracking.trackEvent('ad_click', { ad_type: type, slot_id: slotId });
      }
    } catch (e) { /* silent */ }
  }

  // ── Expose ────────────────────────────────────────────────────────────────

  global.AdManager = {
    renderInlineAd,
    dismissInline,
    requestInterstitial,
    dismissInterstitial,
    requestRewarded,
    _acceptRewarded,
    _declineRewarded,
    trackClick
  };

  console.log('[AdManager] Initialized.');

})(window);
