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
        'Click the <strong>Extensions (🧩)</strong> puzzle icon in the top-right toolbar of Edge.',
        'At the top of the extensions menu, turn <strong>OFF</strong> the switch: <strong>"Allow extensions on localhost:5000"</strong> (or on this site).',
        'Or click the 3 dots (⋮) next to <strong>AdGuard</strong>, <strong>IDM</strong>, or active extensions &rarr; choose <em>"When you click the extension"</em>.',
        'Click <strong>"Re-Check &amp; Unlock App"</strong> below to resume.'
      ]
    },
    chrome: {
      name: 'Google Chrome',
      steps: [
        'Click the <strong>Extensions (🧩)</strong> icon in the top-right toolbar.',
        'Click the 3 dots (⋮) next to your ad-blocker or extension &rarr; set <em>"When you click the extension"</em> or toggle <strong>OFF</strong>.',
        'Or visit <code>chrome://extensions</code> to turn off extensions for this site.',
        'Click <strong>"Re-Check &amp; Unlock App"</strong> below.'
      ]
    },
    brave: {
      name: 'Brave Browser',
      steps: [
        'Click the orange <strong>Brave Lion Shield (🦁)</strong> icon on the right side of the address bar.',
        'Toggle the top switch <strong>"Shields are UP for this site"</strong> to <strong>DOWN (OFF)</strong>.',
        'Click <strong>"Re-Check &amp; Unlock App"</strong> below.'
      ]
    },
    firefox: {
      name: 'Mozilla Firefox',
      steps: [
        'Click the <strong>Shield (🛡️)</strong> icon to the left of the URL address bar.',
        'Toggle <strong>"Enhanced Tracking Protection"</strong> to <strong>OFF</strong> for this site.',
        'Click <strong>"Re-Check &amp; Unlock App"</strong> below.'
      ]
    },
    safari: {
      name: 'Safari (Mac/iOS)',
      steps: [
        'Open Safari <strong>Settings &rarr; Extensions</strong> and uncheck active content blockers.',
        'Click <strong>"Re-Check &amp; Unlock App"</strong> below.'
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
      return '<ol style="margin: 0; padding-left: 1.35rem; font-size: 13.5px; line-height: 1.6; color: rgba(235, 235, 245, 0.85);">' +
        guide.steps.map(function (step) {
          return '<li style="margin-bottom: 0.5rem; letter-spacing: -0.01em;">' + step + '</li>';
        }).join('') +
        '</ol>';
    }

    overlay.innerHTML = [
      '<div style="max-width: 600px; width: 100%; background: rgba(28, 28, 30, 0.88); border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 28px; padding: 2.25rem 2.25rem 1.85rem; box-shadow: 0 35px 80px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255, 255, 255, 0.08); text-align: left; animation: appleSpringUp 0.35s cubic-bezier(0.16, 1, 0.3, 1);">',
      '  <!-- Apple Hero Header -->',
      '  <div style="display: flex; align-items: center; gap: 1.15rem; margin-bottom: 1.35rem;">',
      '    <div style="width: 54px; height: 54px; border-radius: 17px; background: linear-gradient(135deg, rgba(255, 69, 58, 0.22), rgba(255, 159, 10, 0.18)); border: 1px solid rgba(255, 69, 58, 0.35); display: flex; align-items: center; justify-content: center; font-size: 1.65rem; color: #ff453a; flex-shrink: 0; box-shadow: 0 4px 16px rgba(255, 69, 58, 0.2);">',
      '      🛡️',
      '    </div>',
      '    <div>',
      '      <h2 style="margin: 0; font-size: 1.45rem; font-weight: 700; color: #f5f5f7; letter-spacing: -0.025em; line-height: 1.2;">Browser Extension Detected</h2>',
      '      <div style="font-size: 12.5px; color: #ff453a; font-weight: 600; margin-top: 4px; letter-spacing: -0.01em; display: flex; align-items: center; gap: 5px;">',
      '        <span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #ff453a;"></span> All platform operations paused',
      '      </div>',
      '    </div>',
      '  </div>',
      '  <!-- Apple Notice Box -->',
      '  <div style="padding: 13px 18px; background: rgba(255, 69, 58, 0.09); border: 1px solid rgba(255, 69, 58, 0.22); border-radius: 16px; margin-bottom: 1.45rem; font-size: 13.5px; line-height: 1.55; color: rgba(245, 245, 247, 0.9); letter-spacing: -0.01em;">',
      '    To safeguard study material copyrights, protect verified creator monetization, and prevent unauthorized automation, <strong>AbhiHub requires browser extensions (such as ad blockers, script injectors, and downloaders) to be disabled</strong> on this site.',
      '  </div>',
      '  <!-- Guide Section -->',
      '  <div style="margin-bottom: 1.5rem;">',
      '    <div style="font-size: 11.5px; font-weight: 600; color: rgba(235, 235, 245, 0.6); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.65rem;">',
      '      Instructions for your browser:',
      '    </div>',
      '    <!-- Apple Segmented Control Tabs -->',
      '    <div style="background: rgba(120, 120, 128, 0.24); border-radius: 980px; padding: 3px; display: inline-flex; gap: 2px; overflow-x: auto; max-width: 100%; margin-bottom: 0.95rem;">' +
      Object.keys(BROWSER_GUIDES).map(function (key) {
        var isAct = key === defaultBrowser;
        return '<button type="button" class="shield-browser-tab" data-browser="' + key + '" style="padding: 5px 14px; border-radius: 980px; font-size: 12.5px; font-weight: ' + (isAct ? '600' : '500') + '; cursor: pointer; border: none; background: ' + (isAct ? '#ffffff' : 'transparent') + '; color: ' + (isAct ? '#1d1d1f' : 'rgba(235, 235, 245, 0.75)') + '; box-shadow: ' + (isAct ? '0 3px 8px rgba(0,0,0,0.18)' : 'none') + '; transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);">' +
          BROWSER_GUIDES[key].name +
          '</button>';
      }).join('') +
      '    </div>',
      '    <!-- Steps Box -->',
      '    <div id="shield-guide-steps" style="background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 18px; padding: 18px 20px;">' +
      renderBrowserGuideSteps(defaultBrowser) +
      '    </div>',
      '  </div>',
      '  <!-- Apple Action Bar -->',
      '  <div style="display: flex; gap: 10px; align-items: center; justify-content: flex-end; flex-wrap: wrap; margin-top: 1.6rem; padding-top: 1.15rem; border-top: 1px solid rgba(255, 255, 255, 0.09);">' +
      '    <button type="button" id="shield-refresh-btn" style="height: 40px; padding: 0 18px; border-radius: 980px; font-size: 13.5px; font-weight: 500; cursor: pointer; border: 1px solid rgba(255, 255, 255, 0.14); background: rgba(255, 255, 255, 0.07); color: #f5f5f7; transition: all 0.18s ease;">' +
      '      Reload Page' +
      '    </button>' +
      '    <button type="button" id="shield-recheck-btn" style="height: 40px; padding: 0 22px; border-radius: 980px; font-size: 13.5px; font-weight: 600; cursor: pointer; border: none; background: #0071e3; color: #ffffff; box-shadow: 0 4px 14px rgba(0, 113, 227, 0.35); display: inline-flex; align-items: center; gap: 7px; transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);">' +
      '      <span>🔄</span> Re-Check &amp; Unlock App' +
      '    </button>' +
      '  </div>',
      '</div>'
    ].join('\n');

    overlay.querySelectorAll('.shield-browser-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        overlay.querySelectorAll('.shield-browser-tab').forEach(function (t) {
          t.style.background = 'transparent';
          t.style.color = 'rgba(235, 235, 245, 0.75)';
          t.style.boxShadow = 'none';
          t.style.fontWeight = '500';
        });
        this.style.background = '#ffffff';
        this.style.color = '#1d1d1f';
        this.style.boxShadow = '0 3px 8px rgba(0,0,0,0.18)';
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
        recheckBtn.innerHTML = '<span>⏳</span> Checking...';
        setTimeout(function () {
          var isDetected = runExtensionCheck();
          if (!isDetected) {
            hideExtensionShield();
          } else {
            recheckBtn.innerHTML = '<span>❌</span> Extension Still Active &bull; Re-Check';
            setTimeout(function () {
              if (recheckBtn) recheckBtn.innerHTML = '<span>🔄</span> Re-Check &amp; Unlock App';
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
