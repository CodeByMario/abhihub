/**
 * AbhiHub Extension Shield Module (Apple HIG Designed)
 * - Single source of truth for browser extension detection and content protection
 * - Deterrence against ad blockers, download managers (IDM), and script injectors
 * - Differentiates strong deterministic signatures (hard lock) vs weak signals (dismissible banner)
 * - Accessible modal dialog with focus trapping and prefers-reduced-motion support
 * - True document security must be enforced server-side via short-lived signed tokens
 */

(function () {
  'use strict';

  // Idempotency guard: prevent duplicate loading across pages/modules
  if (window.__ABHIHUB_SHIELD_LOADED__) return;
  window.__ABHIHUB_SHIELD_LOADED__ = true;

  /* ── Configuration ───────────────────────────────────────────────────────── */
  const ENABLE_DEV_BYPASS = false;
  const ALLOWED_ORIGIN = window.location.origin;
  const PROBE_URL = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js';
  const PROBE_INTERVAL_MS = 30000;
  const CHECK_INTERVAL_MS = 3000;

  /* ── Internal State & Reference Capture ──────────────────────────────────── */
  let shieldActive = false;
  let warningBannerActive = false;
  let warningDismissed = false;

  let networkProbeFailures = 0;
  let lastProbeTimestamp = 0;
  let lastProbeResult = false;
  let probeInProgress = false;

  let checkIntervalId = null;
  let extObserver = null;
  let previousActiveElement = null;
  let baitElement = null;

  // Capture original network references once at script load
  const originalFetch = window.fetch;
  const originalXhrOpen = (window.XMLHttpRequest && window.XMLHttpRequest.prototype)
    ? window.XMLHttpRequest.prototype.open
    : null;
  let fetchWrapped = false;
  let xhrWrapped = false;

  /* ── Browser Guides Data ─────────────────────────────────────────────────── */
  const BROWSER_GUIDES = {
    edge: {
      name: 'Microsoft Edge',
      steps: [
        'Click the <strong>Extensions</strong> icon in your browser toolbar.',
        'Toggle <strong>"Allow extensions on this site"</strong> to <strong>OFF</strong>.',
        'Or open extension permissions &rarr; set site access to <strong>"When you click the extension"</strong>.',
        'Select <strong>"Verify &amp; Resume"</strong> below.'
      ]
    },
    chrome: {
      name: 'Google Chrome',
      steps: [
        'Click the <strong>Extensions</strong> icon in the top-right toolbar.',
        'Click <strong>More actions (···)</strong> next to your active ad-blocker or extension.',
        'Set site access to <strong>"When you click the extension"</strong> or toggle it <strong>OFF</strong>.',
        'Select <strong>"Verify &amp; Resume"</strong> below.'
      ]
    },
    brave: {
      name: 'Brave',
      steps: [
        'Click the <strong>Brave Shields</strong> icon on the right side of the address bar.',
        'Toggle the top switch <strong>"Shields are UP for this site"</strong> to <strong>DOWN (OFF)</strong>.',
        'Select <strong>"Verify &amp; Resume"</strong> below.'
      ]
    },
    firefox: {
      name: 'Mozilla Firefox',
      steps: [
        'Click the <strong>Shield</strong> icon to the left of the address bar.',
        'Toggle <strong>"Enhanced Tracking Protection"</strong> to <strong>OFF</strong> for this site.',
        'If using an ad-blocker, click its toolbar icon and pause protection for AbhiHub.',
        'Select <strong>"Verify &amp; Resume"</strong> below.'
      ]
    },
    safari: {
      name: 'Safari',
      steps: [
        'On macOS: Navigate to <strong>Safari &rarr; Settings &rarr; Extensions</strong> and uncheck active blockers.',
        'On iOS / iPadOS: Open device <strong>Settings &rarr; Safari &rarr; Extensions</strong> and turn blockers off.',
        'Select <strong>"Verify &amp; Resume"</strong> below.'
      ]
    }
  };

  function detectUserBrowser() {
    const ua = (navigator.userAgent || '').toLowerCase();
    if (ua.includes('edg/')) return 'edge';
    if (ua.includes('brave') || (navigator.brave && typeof navigator.brave.isBrave === 'function')) return 'brave';
    if (ua.includes('firefox/')) return 'firefox';
    if (ua.includes('safari/') && !ua.includes('chrome/')) return 'safari';
    return 'chrome';
  }

  /* ── Network & Process Pausing ───────────────────────────────────────────── */
  function stopAppProcesses() {
    try {
      document.querySelectorAll('video, audio').forEach(function (m) {
        try { m.pause(); } catch (e) {}
      });
    } catch (e) {}

    if (originalFetch && !fetchWrapped) {
      fetchWrapped = true;
      window.fetch = function () {
        if (shieldActive) {
          return Promise.reject(new Error('AbhiHub: Operations paused. Please disable browser extensions.'));
        }
        return originalFetch.apply(this, arguments);
      };
    }

    if (originalXhrOpen && !xhrWrapped) {
      xhrWrapped = true;
      window.XMLHttpRequest.prototype.open = function () {
        if (shieldActive) {
          throw new Error('AbhiHub: Operations paused. Please disable browser extensions.');
        }
        return originalXhrOpen.apply(this, arguments);
      };
    }

    try {
      document.documentElement.style.setProperty('overflow', 'hidden', 'important');
      document.body.style.setProperty('overflow', 'hidden', 'important');
    } catch (e) {}
  }

  function resumeAppProcesses() {
    if (originalFetch && fetchWrapped) {
      window.fetch = originalFetch;
      fetchWrapped = false;
    }
    if (originalXhrOpen && xhrWrapped) {
      window.XMLHttpRequest.prototype.open = originalXhrOpen;
      xhrWrapped = false;
    }
    try {
      document.documentElement.style.removeProperty('overflow');
      document.body.style.removeProperty('overflow');
    } catch (e) {}
  }

  /* ── Reusable Bait Element (Zero Node Leakage) ───────────────────────────── */
  function isBaitHidden() {
    try {
      const parent = document.body || document.documentElement;
      if (!parent) return false;

      if (!baitElement) {
        baitElement = document.createElement('div');
        baitElement.id = 'ad-detector-box';
        baitElement.className = 'adsbygoogle ad-banner pub_300x250 text-ad adsbox banner-ad';
        // Note: No !important on width, height, or display so ad blocker CSS rules can take effect
        baitElement.style.cssText = 'width: 1px; height: 1px; position: absolute; left: -9999px; top: -9999px;';
        baitElement.innerHTML = '&nbsp;';
      }

      if (!baitElement.parentNode) {
        parent.appendChild(baitElement);
      }

      const computed = window.getComputedStyle(baitElement);
      const isHidden = (
        baitElement.offsetHeight === 0 ||
        baitElement.clientHeight === 0 ||
        computed.display === 'none' ||
        computed.visibility === 'hidden' ||
        computed.opacity === '0'
      );

      if (baitElement.parentNode) {
        baitElement.parentNode.removeChild(baitElement);
      }

      return isHidden;
    } catch (e) {
      return false;
    }
  }

  /* ── Network Probe (Throttled, Offline-Safe, Internal Fetch) ─────────────── */
  function probeNetworkAdBlock(force) {
    if (ENABLE_DEV_BYPASS && window.location.search.includes('bypass_shield=1')) {
      return Promise.resolve(false);
    }

    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      return Promise.resolve(lastProbeResult);
    }

    const now = Date.now();
    if (!force && (now - lastProbeTimestamp < PROBE_INTERVAL_MS)) {
      return Promise.resolve(lastProbeResult);
    }

    if (probeInProgress && !force) {
      return Promise.resolve(lastProbeResult);
    }

    probeInProgress = true;
    lastProbeTimestamp = now;

    // Must use originalFetch so it is unaffected by application fetch wrapping
    return originalFetch(PROBE_URL, {
      method: 'HEAD',
      mode: 'no-cors',
      cache: 'no-store'
    }).then(function () {
      probeInProgress = false;
      networkProbeFailures = 0;
      lastProbeResult = false;
      return false;
    }).catch(function () {
      probeInProgress = false;
      networkProbeFailures += 1;
      // Require 2 consecutive failures before marking network block detected
      if (networkProbeFailures >= 2) {
        lastProbeResult = true;
      }
      return lastProbeResult;
    });
  }

  /* ── Strong Deterministic Extension Signatures ───────────────────────────── */
  function hasExtensionSignatures() {
    // 1. Definite ad blocker, IDM, and script-injector DOM elements
    try {
      const selectors = [
        '[id*="adguard"]', '[class*="adguard"]', '[data-adguard]',
        '[id*="ublock"]', '[class*="adblock"]', '[data-adblockkey]',
        '[id*="idm_"]', '[class*="idm_"]', '[id*="idm-"]', 'embed[type*="idm"]',
        '[data-tampermonkey]', '[data-extension-id]', '[data-crx]',
        'script[src^="chrome-extension:"]', 'script[src^="edge-extension:"]', 'script[src^="moz-extension:"]',
        'link[href^="chrome-extension:"]', 'link[href^="edge-extension:"]', 'link[href^="moz-extension:"]',
        'iframe[src^="chrome-extension:"]', 'iframe[src^="edge-extension:"]', 'iframe[src^="moz-extension:"]'
      ];
      if (document.querySelector(selectors.join(','))) {
        return true;
      }
    } catch (e) {}

    // 2. Global extension objects
    try {
      if (
        window.__adguard || window.adguard ||
        window.IDM || window.idm ||
        window.tampermonkey || window.GM || window.GM_info || window.unsafeWindow
      ) {
        return true;
      }
    } catch (e) {}

    // 3. Performance Resource Timing for Extension Origins
    try {
      if (window.performance && typeof window.performance.getEntriesByType === 'function') {
        const resources = window.performance.getEntriesByType('resource');
        for (let i = 0; i < resources.length; i++) {
          const resName = (resources[i].name || '').toLowerCase();
          if (
            resName.startsWith('chrome-extension://') ||
            resName.startsWith('edge-extension://') ||
            resName.startsWith('moz-extension://') ||
            resName.startsWith('safari-extension://') ||
            resName.startsWith('safari-web-extension://')
          ) {
            return true;
          }
        }
      }
    } catch (e) {}

    return false;
  }

  /* ── Evaluation Engine: Strong vs Weak Signals ───────────────────────────── */
  function evaluateEnvironment() {
    if (ENABLE_DEV_BYPASS) {
      if (window.location.search.includes('bypass_shield=1')) return { action: 'none' };
      if (window.location.search.includes('test_extension=1') || window.__TEST_EXTENSION_SHIELD__) {
        return { action: 'lock' };
      }
    }

    // Bypass on auth pages to avoid lockout on login/signup
    const pathname = (window.location.pathname || '').toLowerCase();
    if (
      pathname.startsWith('/login') ||
      pathname.startsWith('/signup') ||
      pathname.startsWith('/register') ||
      pathname.startsWith('/reset-password')
    ) {
      return { action: 'none' };
    }

    // Check strong signals
    if (hasExtensionSignatures()) {
      return { action: 'lock', reason: 'signature' };
    }

    const networkBlocked = lastProbeResult;
    const baitHidden = isBaitHidden();

    // Combined weak signals -> Hard lock
    if (networkBlocked && baitHidden) {
      return { action: 'lock', reason: 'combined_weak' };
    }

    // Single weak signal -> Dismissible warning banner
    if (networkBlocked || baitHidden) {
      return { action: 'warning', reason: networkBlocked ? 'network' : 'cosmetic' };
    }

    return { action: 'none' };
  }

  /* ── Accessible Focus Trap Inside Modal ───────────────────────────────────── */
  function handleFocusTrap(e) {
    if (!shieldActive || e.key !== 'Tab') return;
    const overlay = document.getElementById('abhihub-extension-shield');
    if (!overlay) return;

    const focusable = overlay.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (!focusable.length) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first) {
        last.focus();
        e.preventDefault();
      }
    } else {
      if (document.activeElement === last) {
        first.focus();
        e.preventDefault();
      }
    }
  }

  /* ── UI: Dismissible Warning Banner (Weak Signals) ────────────────────────── */
  function showWarningBanner() {
    if (shieldActive || warningDismissed) return;
    let banner = document.getElementById('abhihub-extension-warning');
    if (!banner) {
      banner = document.createElement('aside');
      banner.id = 'abhihub-extension-warning';
      banner.setAttribute('role', 'status');
      banner.setAttribute('aria-live', 'polite');
      banner.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 2147483640;
        background: #1e293b;
        color: #f8fafc;
        border-bottom: 1px solid rgba(255, 255, 255, 0.15);
        padding: 0.6rem 1rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 0.82rem;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
      `;
      banner.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
          <span><strong>Notice:</strong> An ad blocker or privacy extension may interfere with document viewing on AbhiHub.</span>
        </div>
        <button type="button" id="abhihub-warning-dismiss-btn" aria-label="Dismiss warning" style="background: transparent; border: none; color: #94a3b8; font-size: 1.1rem; cursor: pointer; padding: 0 4px; line-height: 1;">&times;</button>
      `;

      const parent = document.body || document.documentElement;
      if (parent) parent.appendChild(banner);

      const dismissBtn = banner.querySelector('#abhihub-warning-dismiss-btn');
      if (dismissBtn) {
        dismissBtn.addEventListener('click', function () {
          warningDismissed = true;
          hideWarningBanner();
        });
      }
    }
    warningBannerActive = true;
  }

  function hideWarningBanner() {
    const banner = document.getElementById('abhihub-extension-warning');
    if (banner && banner.parentNode) {
      banner.parentNode.removeChild(banner);
    }
    warningBannerActive = false;
  }

  /* ── UI: Full Shield Overlay (Hard Lock) ─────────────────────────────────── */
  function showExtensionShield() {
    const parent = document.body || document.documentElement;
    if (!parent) {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { showExtensionShield(); }, { once: true });
      }
      return;
    }

    hideWarningBanner();

    if (shieldActive && document.getElementById('abhihub-extension-shield')) return;
    shieldActive = true;
    stopAppProcesses();

    // Save active element for focus restoration
    previousActiveElement = document.activeElement;

    // Safe cross-frame communication with explicit origin
    try {
      if (window.top && window.top !== window) {
        window.top.postMessage({ type: 'ABHIHUB_EXTENSION_DETECTED' }, ALLOWED_ORIGIN);
      }
    } catch (e) {}

    let overlay = document.getElementById('abhihub-extension-shield');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'abhihub-extension-shield';
      parent.appendChild(overlay);
    }

    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'shield-dialog-title');

    overlay.style.cssText = [
      'position: fixed !important',
      'inset: 0 !important',
      'width: 100vw !important',
      'height: 100vh !important',
      'z-index: 2147483647 !important',
      'background: rgba(0, 0, 0, 0.78) !important',
      'backdrop-filter: blur(40px) saturate(190%) !important',
      '-webkit-backdrop-filter: blur(40px) saturate(190%) !important',
      'display: flex !important',
      'align-items: center !important',
      'justify-content: center !important',
      'padding: 1.5rem !important',
      'box-sizing: border-box !important',
      'color: #f5f5f7 !important',
      'font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", system-ui, sans-serif !important',
      'overflow-y: auto !important',
      'opacity: 1 !important',
      'transition: opacity 0.25s cubic-bezier(0.16, 1, 0.3, 1) !important'
    ].join(';');

    const defaultBrowser = detectUserBrowser();

    function renderBrowserGuideSteps(browserKey) {
      const guide = BROWSER_GUIDES[browserKey] || BROWSER_GUIDES.edge;
      return '<ol style="margin: 0; padding-left: 1.25rem;">' +
        guide.steps.map(function (step) {
          return '<li style="margin-bottom: 0.5rem; color: #cbd5e1;">' + step + '</li>';
        }).join('') +
        '</ol>';
    }

    overlay.innerHTML = [
      '<style>',
      '  @media (prefers-reduced-motion: reduce) {',
      '    #abhihub-extension-shield, #abhihub-extension-shield * {',
      '      transition: none !important;',
      '      animation: none !important;',
      '    }',
      '  }',
      '</style>',
      '<div style="max-width: 560px; width: 100%; background: #0d121f; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 12px; padding: 2rem 2.25rem; box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6); text-align: left; box-sizing: border-box;">',
      '  <!-- Header Status -->',
      '  <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem; padding-bottom: 0.75rem; border-bottom: 1px solid rgba(255, 255, 255, 0.08);">',
      '    <div style="display: inline-flex; align-items: center; gap: 8px;">',
      '      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
      '      <span style="font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: #ef4444;">Security Verification</span>',
      '    </div>',
      '    <span style="font-size: 0.75rem; color: #64748b; font-weight: 500;">Environment Restricted</span>',
      '  </div>',
      '  <!-- Headline & Policy -->',
      '  <div style="margin-bottom: 1.6rem;">',
      '    <h2 id="shield-dialog-title" style="margin: 0 0 0.5rem 0; font-size: 1.28rem; font-weight: 700; color: #f8fafc; letter-spacing: -0.015em;">Browser Extension Detected</h2>',
      '    <p style="margin: 0; font-size: 0.875rem; line-height: 1.6; color: #94a3b8;">',
      '      To protect academic copyrights, verified creator monetization, and document integrity, AbhiHub requires active extensions (such as ad blockers, script injectors, and downloaders) to be disabled on this domain.',
      '    </p>',
      '  </div>',
      '  <!-- Resolution Instructions -->',
      '  <div style="margin-bottom: 1.75rem;">',
      '    <div style="font-size: 0.72rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.75rem;">',
      '      Disable for your browser',
      '    </div>',
      '    <!-- Underline Tabs -->',
      '    <div style="display: flex; gap: 0.25rem; border-bottom: 1px solid rgba(255, 255, 255, 0.1); margin-bottom: 1.1rem; overflow-x: auto;">' +
      Object.keys(BROWSER_GUIDES).map(function (key) {
        const isAct = key === defaultBrowser;
        return '<button type="button" class="shield-browser-tab" data-browser="' + key + '" style="padding: 0.45rem 0.85rem; font-size: 0.8rem; font-weight: ' + (isAct ? '600' : '500') + '; cursor: pointer; border: none; border-bottom: 2px solid ' + (isAct ? '#3b82f6' : 'transparent') + '; background: transparent; color: ' + (isAct ? '#ffffff' : '#94a3b8') + '; transition: all 0.15s ease; white-space: nowrap;">' +
          BROWSER_GUIDES[key].name +
          '</button>';
      }).join('') +
      '    </div>',
      '    <div id="shield-guide-steps" style="font-size: 0.86rem; line-height: 1.65; color: #cbd5e1;">' +
      renderBrowserGuideSteps(defaultBrowser) +
      '    </div>',
      '  </div>',
      '  <!-- Action Bar -->',
      '  <div style="display: flex; gap: 0.75rem; align-items: center; justify-content: flex-end; padding-top: 1.25rem; border-top: 1px solid rgba(255, 255, 255, 0.08);">',
      '    <button type="button" id="shield-refresh-btn" style="padding: 0.55rem 1.1rem; border-radius: 6px; font-size: 0.84rem; font-weight: 500; cursor: pointer; border: 1px solid rgba(255, 255, 255, 0.15); background: transparent; color: #94a3b8; transition: all 0.15s ease;">',
      '      Reload Page',
      '    </button>',
      '    <button type="button" id="shield-recheck-btn" style="padding: 0.55rem 1.35rem; border-radius: 6px; font-size: 0.84rem; font-weight: 600; cursor: pointer; border: none; background: #2563eb; color: #ffffff; display: inline-flex; align-items: center; gap: 6px; transition: background 0.15s ease;">',
      '      Verify &amp; Resume',
      '    </button>',
      '  </div>',
      '</div>'
    ].join('\n');

    overlay.querySelectorAll('.shield-browser-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        overlay.querySelectorAll('.shield-browser-tab').forEach(function (t) {
          t.style.borderBottom = '2px solid transparent';
          t.style.color = '#94a3b8';
          t.style.fontWeight = '500';
        });
        this.style.borderBottom = '2px solid #3b82f6';
        this.style.color = '#ffffff';
        this.style.fontWeight = '600';
        const bKey = this.getAttribute('data-browser');
        const stepsEl = document.getElementById('shield-guide-steps');
        if (stepsEl) stepsEl.innerHTML = renderBrowserGuideSteps(bKey);
      });
    });

    const refreshBtn = document.getElementById('shield-refresh-btn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        window.location.reload();
      });
    }

    const recheckBtn = document.getElementById('shield-recheck-btn');
    if (recheckBtn) {
      // Focus the recheck button upon modal open
      recheckBtn.focus();

      recheckBtn.addEventListener('click', function () {
        recheckBtn.disabled = true;
        recheckBtn.style.opacity = '0.7';
        recheckBtn.innerText = 'Verifying environment...';

        // Perform immediate un-throttled probe and signature check
        probeNetworkAdBlock(true).then(function () {
          const evalResult = evaluateEnvironment();
          if (evalResult.action !== 'lock') {
            hideExtensionShield();
            if (evalResult.action === 'warning') {
              showWarningBanner();
            }
          } else {
            recheckBtn.innerText = 'Extensions still active — Try again';
            setTimeout(function () {
              if (recheckBtn) {
                recheckBtn.disabled = false;
                recheckBtn.style.opacity = '1';
                recheckBtn.innerHTML = 'Verify &amp; Resume';
              }
            }, 1500);
          }
        });
      });
    }
  }

  function hideExtensionShield() {
    const overlay = document.getElementById('abhihub-extension-shield');
    if (overlay) {
      overlay.style.opacity = '0';
      setTimeout(function () {
        if (overlay && overlay.parentNode) {
          overlay.parentNode.removeChild(overlay);
        }
      }, 250);
    }
    shieldActive = false;
    resumeAppProcesses();

    // Restore focus to element that had focus before modal was shown
    if (previousActiveElement && typeof previousActiveElement.focus === 'function') {
      try { previousActiveElement.focus(); } catch (e) {}
    }
  }

  /* ── Cycle Check ─────────────────────────────────────────────────────────── */
  function runCheck() {
    if (typeof document !== 'undefined' && document.hidden) {
      return;
    }

    probeNetworkAdBlock(false).then(function () {
      const evalResult = evaluateEnvironment();
      if (evalResult.action === 'lock') {
        if (!shieldActive) showExtensionShield();
      } else {
        if (shieldActive) hideExtensionShield();
        if (evalResult.action === 'warning') {
          showWarningBanner();
        } else {
          hideWarningBanner();
        }
      }
    });
  }

  /* ── Cross-Frame PostMessage Listener (Validated Origin) ─────────────────── */
  function onWindowMessage(e) {
    if (e.origin !== ALLOWED_ORIGIN) return;
    if (e.data && e.data.type === 'ABHIHUB_EXTENSION_DETECTED') {
      showExtensionShield();
    }
  }
  window.addEventListener('message', onWindowMessage);

  /* ── Live DOM MutationObserver for Script Injections ─────────────────────── */
  try {
    if (window.MutationObserver) {
      extObserver = new MutationObserver(function (mutations) {
        for (let i = 0; i < mutations.length; i++) {
          const added = mutations[i].addedNodes;
          for (let j = 0; j < added.length; j++) {
            const node = added[j];
            if (node.nodeType === 1) {
              const src = (node.getAttribute && (node.getAttribute('src') || node.getAttribute('href'))) || '';
              if (
                src.startsWith('chrome-extension:') ||
                src.startsWith('edge-extension:') ||
                src.startsWith('moz-extension:')
              ) {
                showExtensionShield();
                return;
              }
            }
          }
        }
      });
      extObserver.observe(document.documentElement, { childList: true, subtree: true });
    }
  } catch (e) {}

  /* ── Keydown Focus Trap Listener ─────────────────────────────────────────── */
  document.addEventListener('keydown', handleFocusTrap, { capture: true });

  /* ── Lifecycle & Timer Management ────────────────────────────────────────── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      setTimeout(runCheck, 100);
    }, { once: true });
  } else {
    setTimeout(runCheck, 100);
  }

  checkIntervalId = setInterval(runCheck, CHECK_INTERVAL_MS);

  /* ── Clean Teardown / Destroy Handler ────────────────────────────────────── */
  function destroy() {
    if (checkIntervalId) {
      clearInterval(checkIntervalId);
      checkIntervalId = null;
    }
    if (extObserver) {
      extObserver.disconnect();
      extObserver = null;
    }

    window.removeEventListener('message', onWindowMessage);
    document.removeEventListener('keydown', handleFocusTrap, { capture: true });

    hideExtensionShield();
    hideWarningBanner();
    resumeAppProcesses();

    if (baitElement && baitElement.parentNode) {
      baitElement.parentNode.removeChild(baitElement);
    }
    baitElement = null;

    window.__ABHIHUB_SHIELD_LOADED__ = false;
  }

  /* ── Public API ──────────────────────────────────────────────────────────── */
  window.showExtensionShield = showExtensionShield;
  window.hideExtensionShield = hideExtensionShield;
  window.AbhiHubShield = {
    show: showExtensionShield,
    hide: hideExtensionShield,
    check: runCheck,
    destroy: destroy
  };
})();
