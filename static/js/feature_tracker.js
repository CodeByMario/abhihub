/**
 * AbhiHub Granular Feature & App Usage Telemetry Engine.
 * Automatically records feature adoption, user actions, device metrics, and network conditions.
 * Uses navigator.sendBeacon and non-blocking batch flushing.
 */
(function () {
  'use strict';

  const BATCH_INTERVAL_MS = 4000;
  const MAX_QUEUE_SIZE = 15;
  const ENDPOINT = '/api/telemetry/track';

  let _eventQueue = [];
  let _flushTimer = null;

  // 1. Device Telemetry Identification
  function getDeviceTelemetry() {
    const ua = navigator.userAgent || '';
    let os = 'Unknown OS';
    if (/android/i.test(ua)) os = 'Android';
    else if (/iphone|ipad|ipod/i.test(ua)) os = 'iOS';
    else if (/windows nt/i.test(ua)) os = 'Windows';
    else if (/macintosh|mac os x/i.test(ua)) os = 'macOS';
    else if (/linux/i.test(ua)) os = 'Linux';

    let browser = 'Unknown Browser';
    if (/edg/i.test(ua)) browser = 'Edge';
    else if (/chrome|crios/i.test(ua)) browser = 'Chrome';
    else if (/firefox|fxios/i.test(ua)) browser = 'Firefox';
    else if (/safari/i.test(ua)) browser = 'Safari';

    let devType = 'desktop';
    if (/mobi|android|touch/i.test(ua) || window.innerWidth < 768) {
      devType = (window.innerWidth >= 768 && window.innerWidth <= 1024) ? 'tablet' : 'mobile';
    }

    return {
      type: devType,
      os: os,
      browser: browser,
      screen: `${window.screen.width}x${window.screen.height}`,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      pixel_ratio: window.devicePixelRatio || 1,
      touch_supported: 'ontouchstart' in window || navigator.maxTouchPoints > 0
    };
  }

  // 2. Network & Performance Telemetry
  function getNetworkTelemetry() {
    const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection || {};
    return {
      effective_type: conn.effectiveType || 'unknown',
      downlink: conn.downlink || null,
      rtt: conn.rtt || null,
      save_data: !!conn.saveData,
      online: navigator.onLine !== false
    };
  }

  // 3. Queue & Flush Mechanism
  function flushEvents() {
    if (_eventQueue.length === 0) return;
    const batch = _eventQueue.splice(0, MAX_QUEUE_SIZE);
    const payload = JSON.stringify({ events: batch });

    if (navigator.sendBeacon) {
      try {
        const blob = new Blob([payload], { type: 'application/json' });
        if (navigator.sendBeacon(ENDPOINT, blob)) return;
      } catch (e) { }
    }

    fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true
    }).catch(function () { });
  }

  function scheduleFlush() {
    if (_flushTimer) return;
    _flushTimer = setTimeout(function () {
      _flushTimer = null;
      flushEvents();
    }, BATCH_INTERVAL_MS);
  }

  // 4. Public API
  window.trackFeature = function (featureName, action, metadata) {
    if (!featureName) return;
    const event = {
      feature: String(featureName).trim().toLowerCase(),
      action: String(action || 'click').trim().toLowerCase(),
      path: window.location.pathname,
      referrer: document.referrer || '',
      device: getDeviceTelemetry(),
      network: getNetworkTelemetry(),
      metadata: metadata || {},
      ts: new Date().toISOString()
    };

    _eventQueue.push(event);
    if (_eventQueue.length >= MAX_QUEUE_SIZE) {
      flushEvents();
    } else {
      scheduleFlush();
    }
  };

  // 4b. Funnel & Drop-off Intent Tracking
  const _activeIntents = {};

  window.startFeatureIntent = function (feature, step, metadata) {
    if (!feature) return;
    _activeIntents[feature] = {
      step: step || 'initiated',
      startTime: Date.now(),
      metadata: metadata || {},
      completed: false
    };
    window.trackFeature(feature, 'initiate', { step: step || 'initiated', ...(metadata || {}) });
  };

  window.completeFeatureIntent = function (feature, metadata) {
    if (!feature) return;
    if (_activeIntents[feature]) {
      _activeIntents[feature].completed = true;
      delete _activeIntents[feature];
    }
    window.trackFeature(feature, 'completed', metadata || {});
  };

  window.abandonFeatureIntent = function (feature, reason, metadata) {
    if (!feature) return;
    const intent = _activeIntents[feature];
    if (intent && !intent.completed) {
      const durationSec = Math.round((Date.now() - intent.startTime) / 1000);
      window.trackFeature(feature, 'abandoned', {
        step: intent.step,
        duration_seconds: durationSec,
        reason: reason || 'navigated_away',
        ...intent.metadata,
        ...(metadata || {})
      });
      delete _activeIntents[feature];
      flushEvents();
    }
  };

  // 5. Automatic Listeners: Pageviews & Delegated Feature Clicks
  window.addEventListener('DOMContentLoaded', function () {
    const path = window.location.pathname.toLowerCase();

    // Auto-detect Upload Initiation
    if (path.includes('/upload')) {
      window.startFeatureIntent('upload', 'opened_upload_form');
      const uploadForm = document.querySelector('form');
      if (uploadForm) {
        uploadForm.addEventListener('submit', function () {
          window.completeFeatureIntent('upload');
        });
      }
      const fileInput = document.querySelector('input[type="file"]');
      if (fileInput) {
        fileInput.addEventListener('change', function () {
          if (fileInput.files && fileInput.files.length) {
            window.startFeatureIntent('upload', 'file_selected', { fileName: fileInput.files[0].name });
          }
        });
      }
    }

    // Auto-detect Search Intent
    const searchInputs = document.querySelectorAll('input[type="search"], input[name="q"], input.search-input');
    searchInputs.forEach(function (input) {
      input.addEventListener('focus', function () {
        window.startFeatureIntent('search', 'focused_search_input');
      });
      input.addEventListener('input', function () {
        if (input.value.trim().length >= 2) {
          window.startFeatureIntent('search', 'typed_query', { query: input.value.trim() });
        }
      });
    });

    // Delegated click for search results vs close
    document.addEventListener('click', function (e) {
      if (e.target.closest('.search-result-item, .search-card, a[href^="/resource/"]')) {
        window.completeFeatureIntent('search');
      }
      if (e.target.closest('.close-search, .search-backdrop, [data-dismiss="search"]')) {
        window.abandonFeatureIntent('search', 'closed_search_drawer');
      }
      // Channel Creation Intent
      if (e.target.closest('[data-action="open-channel-modal"], button:has(.fa-plus-circle)')) {
        window.startFeatureIntent('create_channel', 'opened_modal');
      }
      if (e.target.closest('[data-action="close-channel-modal"], .modal-close')) {
        window.abandonFeatureIntent('create_channel', 'modal_closed');
      }
    }, { passive: true });
    // Record Page Feature View
    const pageFeature = document.body.getAttribute('data-feature') ||
      window.location.pathname.replace(/^\/|\/$/g, '').replace(/\//g, ':') ||
      'landing';
    window.trackFeature(pageFeature, 'page_view');

    // Delegated click listener on interactive feature elements
    document.addEventListener('click', function (e) {
      const target = e.target.closest('[data-feature], [data-action], button, a.btn');
      if (!target) return;

      const feat = target.getAttribute('data-feature') ||
        (target.getAttribute('data-action') ? `action:${target.getAttribute('data-action')}` : null);
      if (feat) {
        window.trackFeature(feat, 'click', {
          tag: target.tagName.toLowerCase(),
          text: (target.innerText || '').slice(0, 40).trim(),
          id: target.id || null
        });
      }
    }, { passive: true });
  });

  // Flush remaining events when navigating away
  window.addEventListener('beforeunload', function () {
    Object.keys(_activeIntents).forEach(function (feat) {
      window.abandonFeatureIntent(feat, 'navigated_away');
    });
  });

  window.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') flushEvents();
  });
  window.addEventListener('pagehide', flushEvents);
})();
