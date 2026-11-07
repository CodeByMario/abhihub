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

  // 5. Automatic Listeners: Pageviews & Delegated Feature Clicks
  window.addEventListener('DOMContentLoaded', function () {
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
  window.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') flushEvents();
  });
  window.addEventListener('pagehide', flushEvents);
})();
