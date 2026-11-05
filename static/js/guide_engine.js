/**
 * Interactive In-App Guide Engine for AbhiHub
 * Apple HIG Redesign: Clean typography, vector SVG icons, zero emojis.
 * Context-Aware: Strictly displays guides relevant to the active page and present DOM elements.
 */
(function () {
  'use strict';

  class GuideEngine {
    constructor() {
      this.currentGuide = null;
      this.currentStepIdx = 0;
      this.allScreenGuides = [];
      this.screenName = '';
      this.overlayEl = null;
      this.spotlightSvg = null;
      this.tooltipEl = null;
      this.menuEl = null;
      this.toastEl = null;
      this._keyHandler = null;
      this._resizeHandler = null;
      this._currentTarget = null;
      this._currentStep = null;
      this._channel = null;

      this.initStyles();
      this.initSyncChannel();
      this.initAuthListeners();
      this.initGlobalTriggers();
    }

    getCurrentScreen() {
      let rawPath = window.location.pathname || '';
      if (rawPath.startsWith('/app-shell')) {
        const p = new URLSearchParams(window.location.search).get('p');
        if (p) rawPath = p.split('?')[0];
      }
      const seg = rawPath.replace(/^\/|\/$/g, '').toLowerCase() || 'dashboard';

      if (seg.startsWith('resource/') || seg.startsWith('pdf/')) return 'pdf-reader';
      if (seg.startsWith('college/')) return 'college';
      if (seg.startsWith('department/')) return 'department';

      const aliases = {
        '': 'dashboard',
        'home': 'dashboard',
        'index': 'dashboard',
        'dashboard': 'dashboard',
        'rank': 'leaderboard',
        'ranking': 'leaderboard',
        'leaderboard': 'leaderboard',
        'profile': 'account',
        'settings': 'account',
        'account': 'account',
        'dashboard/setting': 'account',
        'dashboard/profile': 'account',
        'view': 'pdf-reader',
        'dashboard/view': 'pdf-reader',
        'reader': 'pdf-reader',
        'local-viewer': 'pdf-reader',
        'storeroom': 'store-room',
        'store-room': 'store-room',
        'upload': 'upload'
      };
      return aliases[seg] || seg;
    }

    initSyncChannel() {
      if (typeof BroadcastChannel === 'undefined') return;
      try {
        this._channel = new BroadcastChannel('abhihub_guide_sync');
        this._channel.onmessage = (event) => {
          const { action, guideId, status, step } = event.data || {};
          if (action === 'sync') {
            const targetGuide = this.allScreenGuides.find(g => g.id === guideId);
            if (targetGuide) {
              targetGuide.status = status;
              targetGuide.current_step = step;
            }
            if (this.currentGuide && this.currentGuide.id === guideId) {
              if (status === 'completed' || status === 'dismissed') {
                this.cleanup();
              }
            }
          }
        };
      } catch (e) {
        console.warn('[GuideEngine] BroadcastChannel error:', e);
      }
    }

    initAuthListeners() {
      window.addEventListener('user:logout', () => this.cleanup());
      window.addEventListener('auth:logout', () => this.cleanup());
    }

    initGlobalTriggers() {
      document.addEventListener('click', (e) => {
        const trigger = e.target.closest('[data-action="openAppGuide"], [data-action="openTour"], .btn-open-guide');
        if (trigger) {
          e.preventDefault();
          this.openMenu();
        }
      });
    }

    initStyles() {
      if (document.getElementById('guide-engine-styles')) return;
      const style = document.createElement('style');
      style.id = 'guide-engine-styles';
      style.textContent = `
        /* Apple HIG Spotlight Overlay */
        .guide-spotlight-svg {
          position: fixed;
          top: 0; left: 0;
          width: 100vw; height: 100vh;
          z-index: 99980;
          pointer-events: none;
          transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .guide-spotlight-svg path {
          fill: rgba(15, 23, 42, 0.72);
          pointer-events: auto;
        }
        .guide-highlight-target {
          position: relative !important;
          z-index: 99985 !important;
          outline: 2.5px solid #0071E3 !important;
          outline-offset: 4px !important;
          border-radius: 12px !important;
          box-shadow: 0 0 25px rgba(0, 113, 227, 0.45) !important;
          filter: none !important;
          backdrop-filter: none !important;
        }

        body.guide-body-locked {
          overflow: hidden !important;
        }

        /* Apple HIG Step Tooltip */
        .guide-tooltip {
          position: fixed;
          z-index: 99990;
          background: #ffffff;
          color: #1d1d1f;
          border: 1px solid rgba(0, 0, 0, 0.08);
          border-radius: 16px;
          padding: 16px 18px;
          width: 310px;
          max-width: calc(100vw - 32px);
          box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.25), 0 0 0 1px rgba(0, 0, 0, 0.04);
          font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
          animation: guideTooltipIn 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        [data-theme="dark"] .guide-tooltip {
          background: #1c1c1e;
          color: #f5f5f7;
          border-color: rgba(255, 255, 255, 0.12);
          box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.6);
        }
        @keyframes guideTooltipIn {
          from { opacity: 0; transform: translateY(4px) scale(0.98); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        @media (prefers-reduced-motion: reduce) {
          .guide-spotlight-svg, .guide-tooltip, .guide-menu-card, .guide-backdrop {
            transition: none !important;
            animation: none !important;
          }
        }
        .guide-tooltip h4 {
          margin: 0 0 5px 0;
          font-size: 0.95rem;
          font-weight: 700;
          letter-spacing: -0.015em;
          color: inherit;
        }
        .guide-aim-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          background: rgba(0, 113, 227, 0.08);
          color: #0071E3;
          border-radius: 6px;
          font-size: 0.72rem;
          font-weight: 600;
          padding: 2px 7px;
          margin-bottom: 8px;
          line-height: 1.3;
        }
        [data-theme="dark"] .guide-aim-badge {
          background: rgba(56, 189, 248, 0.15);
          color: #38bdf8;
        }
        .guide-tooltip p {
          margin: 0 0 14px 0;
          font-size: 0.83rem;
          line-height: 1.45;
          color: #6e6e73;
        }
        [data-theme="dark"] .guide-tooltip p {
          color: #a1a1a6;
        }
        .guide-tooltip-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 0.78rem;
          padding-top: 4px;
          border-top: 1px solid rgba(0, 0, 0, 0.06);
        }
        [data-theme="dark"] .guide-tooltip-footer {
          border-top-color: rgba(255, 255, 255, 0.08);
        }
        .guide-counter {
          color: #86868b;
          font-weight: 500;
        }
        .guide-actions {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .guide-btn {
          border: none;
          border-radius: 980px;
          padding: 5px 12px;
          font-size: 0.78rem;
          cursor: pointer;
          font-weight: 600;
          transition: all 0.15s ease;
        }
        .guide-btn-skip {
          background: transparent;
          color: #86868b;
        }
        .guide-btn-skip:hover {
          color: #1d1d1f;
          background: rgba(0, 0, 0, 0.05);
        }
        [data-theme="dark"] .guide-btn-skip:hover {
          color: #f5f5f7;
          background: rgba(255, 255, 255, 0.08);
        }
        .guide-btn-next {
          background: #0071E3;
          color: #ffffff;
        }
        .guide-btn-next:hover {
          background: #0077ED;
          transform: translateY(-1px);
        }

        /* Apple HIG Redesigned Feature Directory Modal */
        .guide-backdrop {
          position: fixed;
          top: 0; left: 0; width: 100vw; height: 100vh;
          background: rgba(15, 23, 42, 0.65);
          backdrop-filter: blur(14px) saturate(180%);
          -webkit-backdrop-filter: blur(14px) saturate(180%);
          z-index: 99980;
          animation: guideBackdropFade 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes guideBackdropFade {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        .guide-menu-card {
          position: fixed;
          top: 50%; left: 50%;
          transform: translate(-50%, -50%);
          z-index: 99992;
          background: #ffffff;
          border: 1px solid rgba(0, 0, 0, 0.08);
          border-radius: 20px;
          width: 92%;
          max-width: 460px;
          padding: 22px 24px;
          color: #1d1d1f;
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(0, 0, 0, 0.04);
          font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, sans-serif;
          animation: guideCardScale 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        }
        [data-theme="dark"] .guide-menu-card {
          background: #1c1c1e;
          border-color: rgba(255, 255, 255, 0.12);
          color: #f5f5f7;
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.65);
        }
        @keyframes guideCardScale {
          from { opacity: 0; transform: translate(-50%, -48%) scale(0.96); }
          to { opacity: 1; transform: translate(-50%, -50%) scale(1); }
        }
        .guide-top-badge {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          padding: 3px 9px;
          background: rgba(0, 113, 227, 0.08);
          color: #0071E3;
          border-radius: 980px;
          font-size: 0.72rem;
          font-weight: 700;
          letter-spacing: 0.04em;
          margin-bottom: 10px;
        }
        [data-theme="dark"] .guide-top-badge {
          background: rgba(56, 189, 248, 0.12);
          color: #38bdf8;
        }
        .guide-menu-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 4px;
        }
        .guide-menu-header h3 {
          margin: 0;
          font-size: 1.28rem;
          font-weight: 700;
          letter-spacing: -0.025em;
          color: inherit;
        }
        .guide-menu-close {
          background: #f5f5f7;
          border: none;
          border-radius: 50%;
          width: 28px;
          height: 28px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #86868b;
          font-size: 1.15rem;
          cursor: pointer;
          transition: all 0.15s ease;
          line-height: 1;
        }
        [data-theme="dark"] .guide-menu-close {
          background: #2c2c2e;
          color: #a1a1a6;
        }
        .guide-menu-close:hover {
          background: #e5e5ea;
          color: #1d1d1f;
        }
        [data-theme="dark"] .guide-menu-close:hover {
          background: #3a3a3c;
          color: #ffffff;
        }
        .guide-menu-desc {
          margin: 0 0 16px 0;
          font-size: 0.85rem;
          color: #6e6e73;
          line-height: 1.45;
        }
        [data-theme="dark"] .guide-menu-desc {
          color: #a1a1a6;
        }
        .guide-menu-list {
          list-style: none;
          padding: 0;
          margin: 0 0 16px 0;
          max-height: 310px;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 9px;
        }
        .guide-menu-item {
          background: #fbfbfd;
          border: 1px solid rgba(0, 0, 0, 0.06);
          border-radius: 14px;
          padding: 13px 15px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          transition: all 0.15s ease;
        }
        [data-theme="dark"] .guide-menu-item {
          background: #2c2c2e;
          border-color: rgba(255, 255, 255, 0.08);
        }
        .guide-menu-item:hover {
          border-color: rgba(0, 113, 227, 0.25);
        }
        .guide-menu-info {
          flex: 1;
          min-width: 0;
        }
        .guide-title-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 3px;
          flex-wrap: wrap;
        }
        .guide-menu-info h5 {
          margin: 0;
          font-size: 0.92rem;
          font-weight: 650;
          color: inherit;
        }
        .guide-tag-completed {
          display: inline-flex;
          align-items: center;
          gap: 3px;
          font-size: 0.7rem;
          font-weight: 600;
          color: #10b981;
          background: rgba(16, 185, 129, 0.1);
          padding: 2px 7px;
          border-radius: 980px;
        }
        .guide-item-aim {
          margin: 0 0 4px 0;
          font-size: 0.8rem;
          color: #6e6e73;
          line-height: 1.38;
        }
        [data-theme="dark"] .guide-item-aim {
          color: #a1a1a6;
        }
        .guide-item-meta {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          font-size: 0.72rem;
          color: #86868b;
          font-weight: 500;
        }
        .guide-menu-actions {
          display: flex;
          align-items: center;
          gap: 6px;
          flex-shrink: 0;
        }
        .btn-guide-start {
          background: #0071E3;
          color: #ffffff;
          padding: 6px 14px;
          font-size: 0.8rem;
        }
        .btn-guide-start:hover {
          background: #0077ED;
          transform: translateY(-1px);
        }
        .guide-menu-footer {
          display: flex;
          justify-content: flex-end;
          padding-top: 6px;
        }
        .guide-btn-done {
          background: #f5f5f7;
          color: #1d1d1f;
          border: 1px solid rgba(0, 0, 0, 0.08);
          padding: 6px 16px;
          font-size: 0.82rem;
        }
        [data-theme="dark"] .guide-btn-done {
          background: #2c2c2e;
          color: #f5f5f7;
          border-color: rgba(255, 255, 255, 0.1);
        }
        .guide-btn-done:hover {
          background: #e5e5ea;
        }
        [data-theme="dark"] .guide-btn-done:hover {
          background: #3a3a3c;
        }

        /* Minimal Toast for Single Tour Completion */
        .guide-toast-pill {
          position: fixed;
          bottom: 24px;
          left: 50%;
          transform: translateX(-50%) translateY(20px);
          opacity: 0;
          z-index: 99995;
          background: #1d1d1f;
          color: #f5f5f7;
          border-radius: 980px;
          padding: 8px 18px;
          font-size: 0.82rem;
          font-weight: 500;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          box-shadow: 0 10px 25px rgba(0, 0, 0, 0.35);
          transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
          pointer-events: none;
        }
        [data-theme="dark"] .guide-toast-pill {
          background: #ffffff;
          color: #1d1d1f;
        }
        .guide-toast-pill.show {
          opacity: 1;
          transform: translateX(-50%) translateY(0);
        }
      `;
      document.head.appendChild(style);
    }

    showToast(message) {
      if (this.toastEl) this.toastEl.remove();
      const toast = document.createElement('div');
      toast.className = 'guide-toast-pill';
      toast.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>
        <span>${message}</span>
      `;
      document.body.appendChild(toast);
      this.toastEl = toast;
      requestAnimationFrame(() => toast.classList.add('show'));
      setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 250);
      }, 2200);
    }

    filterGuidesForCurrentPage(guides) {
      const currentScreen = this.getCurrentScreen();
      return (guides || []).filter(g => {
        // 1. Strict screen match
        const triggerScreen = g.trigger?.screen;
        if (triggerScreen && triggerScreen !== currentScreen) {
          return false;
        }
        // 2. DOM validation: at least one step target must exist on this page right now
        if (g.steps && g.steps.length > 0) {
          const hasTarget = g.steps.some(step => {
            if (!step.target) return false;
            try {
              const el = document.querySelector(step.target);
              return !!(el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0));
            } catch(e) {
              return false;
            }
          });
          if (!hasTarget) return false;
        }
        return true;
      });
    }

    async init(screenName) {
      this.cleanup();
      this.screenName = screenName || this.getCurrentScreen();
      const urlParams = new URLSearchParams(window.location.search);
      let isUrlTriggered = urlParams.has('guide') || urlParams.has('tour') || window.location.hash === '#guide';
      if (!isUrlTriggered && urlParams.has('p')) {
        const pVal = urlParams.get('p') || '';
        if (pVal.includes('guide=') || pVal.includes('tour=')) {
          isUrlTriggered = true;
        }
      }

      try {
        const res = await fetch(`/api/guides/eligible?screen=${encodeURIComponent(this.screenName)}`);
        if (!res.ok) return;
        const data = await res.json();
        const rawGuides = data.guides || [];

        // Filter strictly to current page and verifiable DOM elements
        this.allScreenGuides = this.filterGuidesForCurrentPage(rawGuides);
        if (this.allScreenGuides.length === 0) return;

        if (isUrlTriggered) {
          this.showFeatureMenu(this.allScreenGuides);
        } else {
          const pending = this.allScreenGuides.find(g => g.status !== 'completed' && g.status !== 'dismissed');
          if (pending) {
            const hasActiveModal = () => {
              const el = document.querySelector(
                '.auth-gate-backdrop.active, .ui-feedback-backdrop.active, .popup-overlay:not([style*="display: none"]):not([style*="display:none"]), .file-info-modal-overlay.show, [role="dialog"].show, .modal.show'
              );
              return !!(el && (el.offsetWidth > 0 || el.offsetHeight > 0));
            };

            if (hasActiveModal()) {
              const modalTimer = setInterval(() => {
                if (!hasActiveModal()) {
                  clearInterval(modalTimer);
                  if (!this.currentGuide && !this.menuEl) {
                    this.startGuide(pending);
                  }
                }
              }, 1000);
            } else {
              this.startGuide(pending);
            }
          }
        }
      } catch (e) {
        console.warn('[GuideEngine] Init error:', e);
      }
    }

    showFeatureMenu(guides, title = 'Features on This Page', subtitle = 'Explore interactive guides for the tools on this screen.') {
      this.cleanup();

      // Filter to ensure only current page guides are presented
      const validGuides = this.filterGuidesForCurrentPage(guides);
      if (!validGuides || validGuides.length === 0) {
        this.showToast('Guide completed');
        return;
      }

      document.body.classList.add('guide-body-locked');

      const backdrop = document.createElement('div');
      backdrop.className = 'guide-backdrop';
      backdrop.addEventListener('click', () => this.cleanup());
      document.body.appendChild(backdrop);
      this.overlayEl = backdrop;

      const card = document.createElement('div');
      card.className = 'guide-menu-card';
      card.setAttribute('role', 'dialog');
      card.setAttribute('aria-modal', 'true');
      card.setAttribute('aria-labelledby', 'guide-menu-title');
      this.menuEl = card;

      let itemsHtml = '';
      validGuides.forEach((g, idx) => {
        const name = g.name || g.steps?.[0]?.title || g.id;
        const count = g.steps?.length || 0;
        const aimText = g.aim ? `<p class="guide-item-aim">${g.aim}</p>` : '';
        const isCompleted = g.status === 'completed';
        const isDismissed = g.status === 'dismissed';
        const badge = isCompleted
          ? `<span class="guide-tag-completed"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>Completed</span>`
          : '';

        itemsHtml += `
          <li class="guide-menu-item" style="${isDismissed ? 'opacity:0.4;' : ''}">
            <div class="guide-menu-info">
              <div class="guide-title-row">
                <h5>${name}</h5>
                ${badge}
              </div>
              ${aimText}
              <span class="guide-item-meta">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
                <span>${count} interactive ${count === 1 ? 'step' : 'steps'}</span>
              </span>
            </div>
            <div class="guide-menu-actions">
              <button class="guide-btn guide-btn-skip btn-guide-skip" data-id="${g.id}">Skip</button>
              <button class="guide-btn btn-guide-start" data-idx="${idx}">${isCompleted ? 'Replay' : 'Start'}</button>
            </div>
          </li>
        `;
      });

      card.innerHTML = `
        <div class="guide-top-badge">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon></svg>
          <span>PAGE GUIDE</span>
        </div>
        <div class="guide-menu-header">
          <h3 id="guide-menu-title">${title}</h3>
          <button class="guide-menu-close" id="guide-menu-close" aria-label="Close guides menu">&times;</button>
        </div>
        <p class="guide-menu-desc">${subtitle}</p>
        <ul class="guide-menu-list">${itemsHtml}</ul>
        <div class="guide-menu-footer">
          <button class="guide-btn guide-btn-done" id="guide-menu-dismiss-all">Done</button>
        </div>
      `;

      document.body.appendChild(card);
      this._attachEscape();

      const focusableEls = card.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (focusableEls.length > 0) focusableEls[0].focus();

      card.addEventListener('keydown', (e) => {
        if (e.key !== 'Tab') return;
        const focusables = card.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      });

      card.querySelector('#guide-menu-close').addEventListener('click', () => this.cleanup());
      card.querySelector('#guide-menu-dismiss-all').addEventListener('click', () => this.cleanup());

      card.querySelectorAll('.btn-guide-start').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const idx = parseInt(e.currentTarget.getAttribute('data-idx'), 10);
          const selected = validGuides[idx];
          this.cleanup();
          this.startGuide(selected);
        });
      });

      card.querySelectorAll('.btn-guide-skip').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          const gid = e.currentTarget.getAttribute('data-id');
          await this.syncProgressDirect(gid, 'dismissed', 0, 1);
          const guideObj = validGuides.find(x => x.id === gid);
          if (guideObj) guideObj.status = 'dismissed';
          const li = e.currentTarget.closest('.guide-menu-item');
          if (li) li.style.opacity = '0.35';
          btn.disabled = true;
        });
      });
    }

    startGuide(guide) {
      if (!guide || !guide.steps || guide.steps.length === 0) {
        this.complete();
        return;
      }
      this.currentGuide = guide;
      this.currentStepIdx = guide.current_step || 0;
      this.showStep(this.currentStepIdx);
    }

    renderSpotlight(target) {
      if (this.spotlightSvg) this.spotlightSvg.remove();

      const rect = target.getBoundingClientRect();
      const padding = 6;
      const x = Math.max(0, rect.left - padding);
      const y = Math.max(0, rect.top - padding);
      const w = rect.width + (padding * 2);
      const h = rect.height + (padding * 2);
      const r = 10;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('class', 'guide-spotlight-svg');
      svg.setAttribute('viewBox', `0 0 ${vw} ${vh}`);

      const pathData = `
        M 0 0 H ${vw} V ${vh} H 0 Z
        M ${x + r} ${y}
        H ${x + w - r}
        Q ${x + w} ${y} ${x + w} ${y + r}
        V ${y + h - r}
        Q ${x + w} ${y + h} ${x + w - r} ${y + h}
        H ${x + r}
        Q ${x} ${y + h} ${x} ${y + h - r}
        V ${y + r}
        Q ${x} ${y} ${x + r} ${y}
        Z
      `;

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', pathData);
      path.setAttribute('fill-rule', 'evenodd');
      path.addEventListener('click', () => this.dismiss());

      svg.appendChild(path);
      document.body.appendChild(svg);
      this.spotlightSvg = svg;
    }

    showStep(idx) {
      const steps = this.currentGuide.steps;
      if (idx >= steps.length) {
        this.complete();
        return;
      }

      const step = steps[idx];
      const target = document.querySelector(step.target);

      const isVisible = target && (target.offsetWidth > 0 || target.offsetHeight > 0 || target.getClientRects().length > 0);
      if (!target || !isVisible) {
        if (idx + 1 < steps.length) {
          this.showStep(idx + 1);
        } else {
          this.complete();
        }
        return;
      }

      this.currentStepIdx = idx;
      this.clearHighlight();

      target.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });

      let lastTop = null;
      let sameCount = 0;
      const checkScrollSettled = () => {
        const currentTop = target.getBoundingClientRect().top;
        if (lastTop !== null && Math.abs(currentTop - lastTop) < 1) {
          sameCount++;
        } else {
          sameCount = 0;
        }
        lastTop = currentTop;

        if (sameCount >= 3) {
          this._currentTarget = target;
          this._currentStep = step;
          this.renderSpotlight(target);
          target.classList.add('guide-highlight-target');
          this.renderTooltip(target, step, idx, steps.length);
          this.syncProgress('in_progress', idx);
          this._attachEscape();
          this._attachResize();
        } else {
          requestAnimationFrame(checkScrollSettled);
        }
      };

      requestAnimationFrame(checkScrollSettled);
    }

    renderTooltip(target, step, idx, total) {
      if (this.tooltipEl) this.tooltipEl.remove();

      const rect = target.getBoundingClientRect();
      const tooltip = document.createElement('div');
      tooltip.className = 'guide-tooltip';
      tooltip.setAttribute('role', 'region');
      tooltip.setAttribute('aria-label', `Guide step: ${step.title}`);

      const isLast = idx === total - 1;
      const aimBadge = this.currentGuide?.aim ? `
        <div class="guide-aim-badge">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon></svg>
          <span>Aim: ${this.currentGuide.aim}</span>
        </div>` : '';

      tooltip.innerHTML = `
        ${aimBadge}
        <h4>${step.title}</h4>
        <p>${step.body}</p>
        <div class="guide-tooltip-footer">
          <span class="guide-counter">${idx + 1} of ${total}</span>
          <div class="guide-actions">
            <button class="guide-btn guide-btn-skip" id="guide-btn-skip">Skip</button>
            <button class="guide-btn guide-btn-next" id="guide-btn-next">${isLast ? 'Done' : 'Next'}</button>
          </div>
        </div>
      `;

      document.body.appendChild(tooltip);
      this.tooltipEl = tooltip;

      const tooltipH = tooltip.offsetHeight || 180;
      const tooltipW = tooltip.offsetWidth || 310;
      const margin = 12;

      const below = rect.bottom + margin;
      const above = rect.top - tooltipH - margin;
      const fitsBelow = below + tooltipH <= window.innerHeight - 8;
      const top = fitsBelow ? below : Math.max(8, above);
      const left = Math.max(12, Math.min(rect.left, window.innerWidth - tooltipW - 12));

      tooltip.style.top = `${top}px`;
      tooltip.style.left = `${left}px`;

      tooltip.querySelector('#guide-btn-skip').addEventListener('click', () => this.dismiss());
      tooltip.querySelector('#guide-btn-next').addEventListener('click', () => this.showStep(idx + 1));
    }

    clearHighlight() {
      document.querySelectorAll('.guide-highlight-target').forEach(el => el.classList.remove('guide-highlight-target'));
      if (this.spotlightSvg) {
        this.spotlightSvg.remove();
        this.spotlightSvg = null;
      }
    }

    cleanup() {
      document.body.classList.remove('guide-body-locked');
      this.clearHighlight();
      this._currentTarget = null;
      this._currentStep = null;
      if (this._keyHandler) {
        document.removeEventListener('keydown', this._keyHandler);
        this._keyHandler = null;
      }
      if (this._resizeHandler) {
        window.removeEventListener('resize', this._resizeHandler);
        window.removeEventListener('scroll', this._resizeHandler);
        this._resizeHandler = null;
      }
      if (this.overlayEl) {
        this.overlayEl.remove();
        this.overlayEl = null;
      }
      if (this.tooltipEl) {
        this.tooltipEl.remove();
        this.tooltipEl = null;
      }
      if (this.menuEl) {
        this.menuEl.remove();
        this.menuEl = null;
      }
    }

    _attachEscape() {
      if (this._keyHandler) {
        document.removeEventListener('keydown', this._keyHandler);
      }
      this._keyHandler = (e) => {
        if (e.key === 'Escape') this.cleanup();
      };
      document.addEventListener('keydown', this._keyHandler);
    }

    _attachResize() {
      if (this._resizeHandler) return;
      let rafId = null;
      this._resizeHandler = () => {
        if (rafId) cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(() => {
          if (!this._currentTarget || !this.tooltipEl) return;
          this.renderSpotlight(this._currentTarget);
          this.renderTooltip(this._currentTarget, this._currentStep, this.currentStepIdx, this.currentGuide?.steps?.length || 1);
        });
      };
      window.addEventListener('resize', this._resizeHandler, { passive: true });
      window.addEventListener('scroll', this._resizeHandler, { passive: true });
    }

    async syncProgressDirect(guideId, status, step = 0, version = 1) {
      try {
        const res = await fetch(`/api/guides/${encodeURIComponent(guideId)}/progress`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status, current_step: step, version })
        });
        if (res.status === 401 || res.status === 403) {
          this.cleanup();
          return;
        }
        if (this._channel) {
          try {
            this._channel.postMessage({ action: 'sync', guideId, status, step });
          } catch (_) {}
        }
      } catch (e) {
        console.warn('[GuideEngine] Progress sync failed:', e);
      }
    }

    async syncProgress(status, step = 0) {
      if (!this.currentGuide) return;
      return this.syncProgressDirect(this.currentGuide.id, status, step, this.currentGuide.version || 1);
    }

    complete() {
      this.syncProgress('completed', this.currentStepIdx);
      if (this.currentGuide) {
        this.currentGuide.status = 'completed';
      }
      this.cleanup();

      // Check remaining valid guides strictly for the current page
      const pageGuides = this.filterGuidesForCurrentPage(this.allScreenGuides);
      const remaining = pageGuides.filter(g => g.status !== 'completed' && g.status !== 'dismissed');

      if (remaining.length > 0) {
        this.showFeatureMenu(
          pageGuides,
          'Guide Finished',
          'Explore another interactive feature on this page or tap Done.'
        );
      } else {
        this.showToast('Tour completed');
      }
    }

    dismiss() {
      this.syncProgress('dismissed', this.currentStepIdx);
      if (this.currentGuide) {
        this.currentGuide.status = 'dismissed';
      }
      this.cleanup();

      const pageGuides = this.filterGuidesForCurrentPage(this.allScreenGuides);
      const remaining = pageGuides.filter(g => g.status !== 'completed' && g.status !== 'dismissed');
      if (remaining.length > 0) {
        this.showFeatureMenu(
          pageGuides,
          'Features on This Page',
          'Choose another feature to explore, or tap Done.'
        );
      }
    }

    openMenu() {
      const pageGuides = this.filterGuidesForCurrentPage(this.allScreenGuides);
      if (pageGuides && pageGuides.length > 0) {
        this.showFeatureMenu(pageGuides);
      } else {
        this.init(this.getCurrentScreen());
      }
    }

    startGuideById(guideId) {
      const guide = this.allScreenGuides.find(g => g.id === guideId);
      if (guide) {
        this.cleanup();
        this.startGuide(guide);
      }
    }
  }

  window.GuideEngine = new GuideEngine();
})();
