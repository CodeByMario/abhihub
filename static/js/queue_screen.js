/**
 * Queue Waiting Screen Client & Telemetry
 * Handles queue waiting modal, real-time polling, honest ETA countdown,
 * study tips, and beacon telemetry.
 */
(function() {
  const TELEMETRY_URL = '/api/telemetry/wait-event';
  let activeQid = null;
  let pollTimer = null;
  let isWaiting = false;
  let adsRendered = false;

  window.renderQueueAd = function(adsConfig) {
    if (adsRendered || !adsConfig || !adsConfig.slots || !adsConfig.slots.length) return;
    adsRendered = true;

    const delayMs = (adsConfig.delay_s || 3) * 1000;
    setTimeout(() => {
      // Re-verify modal is still waiting (do not render if already ready or closed)
      if (!isWaiting) return;

      const adSection = document.getElementById('queue-ad-section');
      const frameWrap = document.getElementById('queue-ad-frame-wrap');
      if (!adSection || !frameWrap) return;

      adSection.style.display = 'block';
      frameWrap.innerHTML = '';

      // Hard cap: max 3 ads
      const slots = adsConfig.slots.slice(0, 3);
      slots.forEach(slot => {
        const iframe = document.createElement('iframe');
        iframe.src = `/ad-frame.html?slot=${encodeURIComponent(slot)}`;
        iframe.sandbox = 'allow-scripts allow-popups allow-popups-to-escape-sandbox';
        iframe.loading = 'lazy';
        iframe.title = 'Advertisement';
        iframe.style.border = 'none';

        if (slot === '300x250') {
          iframe.width = '300';
          iframe.height = '250';
        } else if (slot === '728x90') {
          iframe.width = '728';
          iframe.height = '90';
        } else if (slot === '468x60') {
          iframe.width = '468';
          iframe.height = '60';
        } else if (slot === '320x50') {
          iframe.width = '320';
          iframe.height = '50';
        } else {
          iframe.width = '100%';
          iframe.height = '250';
        }

        frameWrap.appendChild(iframe);
      });

      sendTelemetry('ads_shown', { slots: slots, level: adsConfig.level });
    }, delayMs);
  };

  function sendTelemetry(eventName, extraData = {}) {
    const payload = JSON.stringify({
      event: eventName,
      qid: activeQid,
      timestamp: Date.now(),
      ...extraData
    });
    if (navigator.sendBeacon) {
      const blob = new Blob([payload], { type: 'application/json' });
      navigator.sendBeacon(TELEMETRY_URL, blob);
    } else {
      fetch(TELEMETRY_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: true
      }).catch(() => {});
    }
  }

  // Study tips rotation
  const STUDY_TIPS = [
    "Reviewing previous year questions (PYQs) 48h before exams boosts retention by up to 35%.",
    "Active recall using handwritten summary notes beats passive re-reading by 2x.",
    "Solve numericals with step-by-step LaTeX formulas to maximize partial exam marks.",
    "Two-sided exam paper stitcher in AbhiHub automatically stitches front & back question papers.",
    "Uploading 1 study document grants +10 daily AI queries and +19 paper unlock credits!"
  ];

  function getStudyTip() {
    return STUDY_TIPS[Math.floor(Math.random() * STUDY_TIPS.length)];
  }

  function createQueueModal() {
    if (document.getElementById('queue-waiting-modal')) return;

    const modal = document.createElement('div');
    modal.id = 'queue-waiting-modal';
    modal.className = 'queue-modal-overlay';
    modal.style.display = 'none';

    modal.innerHTML = `
      <div class="queue-modal-card" role="dialog" aria-labelledby="queue-title" aria-modal="true">
        <!-- 1. Header: Position + ETA + Progress -->
        <div class="queue-header">
          <div class="queue-status-badge">
            <span class="queue-pulse-dot"></span>
            <span id="queue-badge-text">In Queue</span>
          </div>
          <h3 id="queue-title" class="queue-title">Campus AI Capacity Queue</h3>
          <p class="queue-subtitle">OpenRouter free pool limit: 15 queries/min. You will be admitted automatically.</p>
        </div>

        <div class="queue-stats-box">
          <div class="queue-stat">
            <span class="queue-stat-label">Your Position</span>
            <span class="queue-stat-value" id="queue-pos-val">#1</span>
          </div>
          <div class="queue-stat">
            <span class="queue-stat-label">Estimated Wait</span>
            <span class="queue-stat-value" id="queue-eta-val">~4s</span>
          </div>
        </div>

        <div class="queue-progress-bar-wrap">
          <div class="queue-progress-bar" id="queue-progress-fill" style="width: 25%;"></div>
        </div>

        <!-- 2. Skip the line Upsell Button -->
        <div class="queue-action-primary">
          <button type="button" class="queue-btn-premium" id="queue-btn-skip">
            ⚡ Skip the line with Premium
            <span class="queue-btn-sub">Instant AI • No Waiting • 30/day</span>
          </button>
        </div>

        <!-- 3. Alternatives (On-device, BYOK) -->
        <div class="queue-alternatives">
          <span class="queue-alt-title">Or use instant alternatives:</span>
          <div class="queue-alt-buttons">
            <button type="button" class="queue-btn-secondary" id="queue-btn-webllm">
              🤖 On-Device AI (WebLLM - Free)
            </button>
            <button type="button" class="queue-btn-secondary" id="queue-btn-byok">
              🔑 Use Your Own API Key
            </button>
          </div>
        </div>

        <!-- 4. Useful Study Content -->
        <div class="queue-study-nugget">
          <div class="queue-nugget-icon">💡</div>
          <div class="queue-nugget-body">
            <strong>Study Nugget:</strong>
            <p id="queue-study-tip-text">${getStudyTip()}</p>
            <a href="/store-room" class="queue-nugget-link" target="_blank" rel="noopener">Browse Store Room PYQs →</a>
          </div>
        </div>

        <!-- 5. Ads Container (LAST and visually separated away from buttons) -->
        <div class="queue-ad-section" id="queue-ad-section" style="display: none;">
          <div class="queue-ad-label">SPONSORED / ADVERTISEMENT</div>
          <div class="queue-ad-frame-wrapper" id="queue-ad-frame-wrap">
            <!-- Adsterra sandboxed iframe rendered here in Phase 5 -->
          </div>
        </div>

        <div class="queue-footer">
          <button type="button" class="queue-btn-cancel" id="queue-btn-cancel">Leave Queue</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    // Event listeners
    document.getElementById('queue-btn-skip').addEventListener('click', () => {
      sendTelemetry('upsell_clicked');
      window.location.href = '/settings#premium';
    });

    document.getElementById('queue-btn-webllm').addEventListener('click', () => {
      hideQueueModal();
      if (window.AIRouter && window.AIRouter.switchToWebLlm) {
        window.AIRouter.switchToWebLlm();
      } else {
        alert('Switching to on-device WebLLM mode for private, zero-queue answers.');
      }
    });

    document.getElementById('queue-btn-byok').addEventListener('click', () => {
      hideQueueModal();
      window.location.href = '/settings#api-keys';
    });

    document.getElementById('queue-btn-cancel').addEventListener('click', () => {
      sendTelemetry('abandoned');
      hideQueueModal();
    });
  }

  function showQueueModal(qid, position, etaS) {
    createQueueModal();
    activeQid = qid;
    isWaiting = true;

    const modal = document.getElementById('queue-waiting-modal');
    modal.style.display = 'flex';

    updateQueueUI(position, etaS);
    sendTelemetry('wait_started', { initial_position: position, eta_s: etaS });

    // Track tab abandonment on unload
    window.addEventListener('beforeunload', handleUnload);
  }

  function updateQueueUI(position, etaS) {
    const posVal = document.getElementById('queue-pos-val');
    const etaVal = document.getElementById('queue-eta-val');
    const progFill = document.getElementById('queue-progress-fill');

    const realEta = etaS !== undefined ? etaS : (position * 4);
    if (posVal) posVal.textContent = `#${position}`;
    if (etaVal) etaVal.textContent = `~${Math.max(1, realEta)}s`;

    if (progFill) {
      // Progress from far back (10%) to front (90%)
      const pct = Math.max(15, Math.min(95, 100 - (position * 15)));
      progFill.style.width = `${pct}%`;
    }
  }

  function hideQueueModal() {
    isWaiting = false;
    adsRendered = false;
    clearTimeout(pollTimer);
    window.removeEventListener('beforeunload', handleUnload);

    const frameWrap = document.getElementById('queue-ad-frame-wrap');
    if (frameWrap) frameWrap.innerHTML = '';
    const adSection = document.getElementById('queue-ad-section');
    if (adSection) adSection.style.display = 'none';

    const modal = document.getElementById('queue-waiting-modal');
    if (modal) modal.style.display = 'none';
  }

  function handleUnload() {
    if (isWaiting && activeQid) {
      sendTelemetry('abandoned');
    }
  }

  /**
   * Main Queue Wait Coordinator
   * Polls /api/queue/status until ticket is ready.
   */
  async function waitForQueueTicket(qid, initialPos, initialEta) {
    showQueueModal(qid, initialPos, initialEta);

    return new Promise((resolve, reject) => {
      async function poll() {
        if (!isWaiting) {
          reject(new Error('Queue cancelled by user'));
          return;
        }

        try {
          const resp = await fetch(`/api/queue/status/${qid}`);
          if (!resp.ok) {
            hideQueueModal();
            reject(new Error(`Queue poll failed (${resp.status})`));
            return;
          }

          const data = await resp.json();
          if (data.status === 'ready' && data.ticket) {
            hideQueueModal();
            resolve(data.ticket);
            return;
          } else if (data.status === 'waiting') {
            updateQueueUI(data.position, data.eta_s);
            // Render ads if configured in data.ads (Phase 5)
            if (data.ads && window.renderQueueAd) {
              window.renderQueueAd(data.ads);
            }
            const delay = (data.poll_in || 2) * 1000;
            pollTimer = setTimeout(poll, delay);
          } else {
            hideQueueModal();
            reject(new Error(data.message || 'Queue session expired'));
          }
        } catch (err) {
          hideQueueModal();
          reject(err);
        }
      }

      // First poll after initial eta or 2 seconds
      const firstDelay = (initialPos <= 1 ? 2 : 3) * 1000;
      pollTimer = setTimeout(poll, firstDelay);
    });
  }

  // Expose global queue helper
  window.AbhiHubQueue = {
    joinAndAcquireTicket: async function(op = 'ai') {
      const resp = await fetch('/api/queue/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ op: op })
      });

      if (!resp.ok && resp.status !== 503) {
        throw new Error(`Queue join failed (${resp.status})`);
      }

      const data = await resp.json();
      if (data.status === 'ready') {
        return data.ticket;
      } else if (data.status === 'waiting') {
        return await waitForQueueTicket(data.qid, data.position, data.eta_s);
      } else if (data.status === 'exhausted') {
        throw new Error('Daily free AI capacity is fully exhausted. Please upgrade to Premium or use On-Device WebLLM.');
      } else {
        throw new Error(data.message || 'Unable to join queue');
      }
    },
    sendTelemetry: sendTelemetry
  };
})();
