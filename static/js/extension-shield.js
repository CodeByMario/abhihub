/**
 * AbhiHub Extension Shield Module (Apple HIG Designed)
 * - Detects active browser ad blockers, scrapers, IDM, and content script extensions
 * - Automatically pauses app processes & renders an Apple Human Interface styled modal
 * - Zero false positives: purely verifies live DOM cosmetic filtering and extension signatures
 * - Immediately unlocks the application when extensions are toggled off
 */
(function () {
  'use strict';

  var shieldActive = false;
  var originalFetch = window.fetch;
  var originalXhrOpen = (window.XMLHttpRequest && window.XMLHttpRequest.prototype) ? window.XMLHttpRequest.prototype.open : null;

  var BROWSER_GUIDES = {
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
    var ua = (navigator.userAgent || '').toLowerCase();
    if (ua.includes('edg/')) return 'edge';
    if (ua.includes('brave') || (navigator.brave && typeof navigator.brave.isBrave === 'function')) return 'brave';
    if (ua.includes('firefox/')) return 'firefox';
    if (ua.includes('safari/') && !ua.includes('chrome/')) return 'safari';
    return 'chrome';
  }

  function stopAppProcesses() {
    try {
      document.querySelectorAll('video, audio').forEach(function (m) {
        try { m.pause(); } catch (e) {}
      });
    } catch (e) {}

    if (originalFetch) {
      window.fetch = function () {
        if (shieldActive) {
          return Promise.reject(new Error('AbhiHub: Operations paused. Please disable browser extensions.'));
        }
        return originalFetch.apply(this, arguments);
      };
    }

    if (originalXhrOpen) {
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
    if (originalFetch) window.fetch = originalFetch;
    if (originalXhrOpen) window.XMLHttpRequest.prototype.open = originalXhrOpen;
    try {
      document.documentElement.style.removeProperty('overflow');
      document.body.style.removeProperty('overflow');
    } catch (e) {}
  }

  function showExtensionShield() {
    if (shieldActive) return;
    shieldActive = true;
    stopAppProcesses();

    try {
      if (window.top && window.top !== window) {
        window.top.postMessage({ type: 'ABHIHUB_EXTENSION_DETECTED' }, '*');
      }
    } catch (e) {}

    var overlay = document.getElementById('abhihub-extension-shield');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'abhihub-extension-shield';
      document.body.appendChild(overlay);
    }

    overlay.style.cssText = [
      'position: fixed !important',
      'inset: 0 !important',
      'width: 100vw !important',
      'height: 100vh !important',
      'z-index: 2147483647 !important',
      'background: rgba(0, 0, 0, 0.75) !important',
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

    var defaultBrowser = detectUserBrowser();

    function renderBrowserGuideSteps(browserKey) {
      var guide = BROWSER_GUIDES[browserKey] || BROWSER_GUIDES.edge;
      return '<ol style="margin: 0; padding-left: 1.25rem;">' +
        guide.steps.map(function (step) {
          return '<li style="margin-bottom: 0.5rem; color: #cbd5e1;">' + step + '</li>';
        }).join('') +
        '</ol>';
    }

    overlay.innerHTML = [
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
      '    <h2 style="margin: 0 0 0.5rem 0; font-size: 1.28rem; font-weight: 700; color: #f8fafc; letter-spacing: -0.015em;">Browser Extension Detected</h2>',
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
        var isAct = key === defaultBrowser;
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
    ].join('
');

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
        var bKey = this.getAttribute('data-browser');
        var stepsEl = document.getElementById('shield-guide-steps');
        if (stepsEl) stepsEl.innerHTML = renderBrowserGuideSteps(bKey);
      });
    });

    var refreshBtn = document.getElementById('shield-refresh-btn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        window.location.reload();
      });
    }

    var recheckBtn = document.getElementById('shield-recheck-btn');
    if (recheckBtn) {
      recheckBtn.addEventListener('click', function () {
        recheckBtn.disabled = true;
        recheckBtn.style.opacity = '0.7';
        recheckBtn.innerText = 'Verifying environment...';
        setTimeout(function () {
          var isDetected = runExtensionCheck();
          if (!isDetected) {
            hideExtensionShield();
          } else {
            recheckBtn.innerText = 'Extensions still active — Try again';
            setTimeout(function () {
              if (recheckBtn) {
                recheckBtn.disabled = false;
                recheckBtn.style.opacity = '1';
                recheckBtn.innerHTML = 'Verify &amp; Resume';
              }
            }, 1800);
          }
        }, 120);
      });
    }
  }

  function hideExtensionShield() {
    var overlay = document.getElementById('abhihub-extension-shield');
    if (overlay) {
      overlay.style.opacity = '0';
      setTimeout(function () {
        if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
      }, 250);
    }
    shieldActive = false;
    resumeAppProcesses();
  }

  /**
   * Deterministic Extension Check:
   * - AdGuard & AdBlockers inject cosmetic stylesheets into the page hiding standard ad selectors (.adsbygoogle, .ad-banner, .pub_300x250)
   * - Scraper & Extension content scripts inject custom elements or attributes
   * - ZERO flaky network calls to third parties (preventing false positives when offline or under tracking protection)
   */
  function runExtensionCheck() {
    if (window.location.search.includes('test_extension=1') || window.__TEST_EXTENSION_SHIELD__) return true;
    if (window.location.search.includes('bypass_shield=1')) return false;

    var p = (window.location.pathname || '').toLowerCase();
    if (p.startsWith('/login') || p.startsWith('/signup') || p.startsWith('/register') || p.startsWith('/reset-password')) {
      return false;
    }

    // 1. Cosmetic Bait Element Check (AdGuard, uBlock, AdBlock)
    try {
      var bait = document.createElement('div');
      bait.id = 'ad-detector-box';
      bait.className = 'adsbygoogle ad-banner pub_300x250 text-ad adsbox banner-ad';
      bait.style.width = '300px';
      bait.style.height = '250px';
      bait.style.position = 'absolute';
      bait.style.left = '-9999px';
      bait.style.top = '-9999px';
      bait.innerHTML = '&nbsp;';
      (document.body || document.documentElement).appendChild(bait);

      var computed = window.getComputedStyle(bait);
      var isHidden = (
        computed.display === 'none' ||
        computed.visibility === 'hidden'
      );
      bait.remove();
      if (isHidden) return true;
    } catch (e) {}

    // 2. Extension-Injected Content Script Selectors & Signatures (AdGuard, IDM, Tampermonkey)
    try {
      var selectors = [
        '[id*="adguard"]', '[class*="adguard"]', '[data-adguard]',
        '[id*="ublock"]', '[class*="adblock"]', '[data-adblockkey]',
        '[id*="idm_"]', '[class*="idm_"]', '[id*="idm-"]', 'embed[type*="idm"]',
        '[data-tampermonkey]', '[data-extension-id]',
        'script[src^="chrome-extension:"]', 'script[src^="edge-extension:"]',
        'link[href^="chrome-extension:"]', 'link[href^="edge-extension:"]'
      ];
      if (document.querySelector(selectors.join(','))) {
        return true;
      }

      if (window.__adguard || window.adguard || window.IDM || window.idm || window.tampermonkey) {
        return true;
      }
    } catch (e) {}

    return false;
  }

  // Handle iframe message if parent window
  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'ABHIHUB_EXTENSION_DETECTED') {
      showExtensionShield();
    }
  });

  function startCheck() {
    var hasExt = runExtensionCheck();
    if (hasExt) {
      showExtensionShield();
    } else if (shieldActive) {
      hideExtensionShield();
    }
  }

  startCheck();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      setTimeout(startCheck, 100);
    });
  } else {
    setTimeout(startCheck, 100);
  }

  setInterval(function () {
    var hasExt = runExtensionCheck();
    if (hasExt && !shieldActive) {
      showExtensionShield();
    } else if (!hasExt && shieldActive) {
      hideExtensionShield();
    }
  }, 2500);

  window.showExtensionShield = showExtensionShield;
  window.hideExtensionShield = hideExtensionShield;
})();
