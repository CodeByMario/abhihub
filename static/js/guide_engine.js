/**
 * Interactive In-App Guide Engine for AbhiHub
 * Fixed: SVG Spotlight Cutout (crystal-clear target, no blur on highlighted element)
 * Added: Post-Guide Completion Menu (allows immediately selecting another guide)
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
        /* SVG Spotlight Overlay */
        .guide-spotlight-svg {
          position: fixed;
          top: 0; left: 0;
          width: 100vw; height: 100vh;
          z-index: 99980;
          pointer-events: none;
          transition: all 0.25s ease;
        }
        .guide-spotlight-svg path {
          fill: rgba(15, 23, 42, 0.78);
          pointer-events: auto;
        }
        .guide-highlight-target {
          position: relative !important;
          z-index: 99985 !important;
          outline: 3px solid #6366f1 !important;
          outline-offset: 4px !important;
          border-radius: 8px !important;
          box-shadow: 0 0 20px rgba(99, 102, 241, 0.6) !important;
          filter: none !important;
          backdrop-filter: none !important;
        }

        body.guide-body-locked {
          overflow: hidden !important;
        }

        /* Tooltip styling */
        .guide-tooltip {
          position: fixed;
          z-index: 99990;
          background: #1e293b;
          color: #f8fafc;
          border: 1px solid #334155;
          border-radius: 12px;
          padding: 16px;
          width: 300px;
          max-width: calc(100vw - 32px);
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);
          font-family: inherit;
        }
        @media (prefers-reduced-motion: reduce) {
          .guide-spotlight-svg, .guide-tooltip, .guide-menu-card, .guide-backdrop {
            transition: none !important;
            animation: none !important;
          }
        }
        .guide-tooltip h4 {
          margin: 0 0 6px 0;
          font-size: 15px;
          font-weight: 600;
          color: #ffffff;
        }
        .guide-aim-badge {
          display: inline-block;
          background: rgba(99, 102, 241, 0.18);
          color: #818cf8;
          border: 1px solid rgba(99, 102, 241, 0.35);
          font-size: 11px;
          font-weight: 500;
          border-radius: 4px;
          padding: 2px 7px;
          margin-bottom: 8px;
          line-height: 1.3;
        }
        .guide-tooltip p {
          margin: 0 0 14px 0;
          font-size: 13px;
          line-height: 1.4;
          color: #94a3b8;
        }
        .guide-tooltip-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 12px;
        }
        .guide-counter {
          color: #64748b;
          font-weight: 500;
        }
        .guide-actions {
          display: flex;
          gap: 8px;
        }
        .guide-btn {
          border: none;
          border-radius: 6px;
          padding: 6px 12px;
          font-size: 12px;
          cursor: pointer;
          font-weight: 500;
          transition: background 0.15s ease;
        }
        .guide-btn-skip {
          background: transparent;
          color: #94a3b8;
        }
        .guide-btn-skip:hover { color: #f8fafc; }
        .guide-btn-next {
          background: #6366f1;
          color: #ffffff;
        }
        .guide-btn-next:hover { background: #4f46e5; }

        /* Feature Directory & Completion Modal */
        .guide-backdrop {
          position: fixed;
          top: 0; left: 0; width: 100vw; height: 100vh;
          background: rgba(15, 23, 42, 0.75);
          z-index: 99980;
        }
        .guide-menu-card {
          position: fixed;
          top: 50%; left: 50%;
          transform: translate(-50%, -50%);
          z-index: 99992;
          background: #1e293b;
          border: 1px solid #334155;
          border-radius: 14px;
          width: 90%;
          max-width: 440px;
          padding: 20px;
          color: #f8fafc;
          box-shadow: 0 20px 35px rgba(0, 0, 0, 0.6);
          font-family: inherit;
        }
        .guide-menu-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 10px;
        }
        .guide-menu-header h3 {
          margin: 0;
          font-size: 17px;
          font-weight: 700;
          color: #f8fafc;
        }
        .guide-menu-close {
          background: transparent;
          border: none;
          color: #94a3b8;
          font-size: 20px;
          cursor: pointer;
          line-height: 1;
        }
        .guide-menu-close:hover { color: #ffffff; }
        .guide-menu-desc {
          margin: 0 0 16px 0;
          font-size: 13px;
          color: #94a3b8;
          line-height: 1.4;
        }
        .guide-menu-list {
          list-style: none;
          padding: 0;
          margin: 0 0 16px 0;
          max-height: 280px;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .guide-menu-item {
          background: #0f172a;
          border: 1px solid #334155;
          border-radius: 8px;
          padding: 12px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
        }
        .guide-menu-info h5 {
          margin: 0 0 4px 0;
          font-size: 14px;
          color: #f1f5f9;
        }
        .guide-menu-info p {
          margin: 0;
          font-size: 12px;
          color: #64748b;
        }
        .guide-menu-actions {
          display: flex;
          gap: 6px;
        }
      `;
      document.head.appendChild(style);
    }

    async init(screenName) {
      this.cleanup();
      this.screenName = screenName || '';
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
        this.allScreenGuides = data.guides || [];

        if (this.allScreenGuides.length === 0) return;

        if (isUrlTriggered) {
          this.showFeatureMenu(this.allScreenGuides);
        } else {
          const pending = this.allScreenGuides.find(g => g.status !== 'completed' && g.status !== 'dismissed');
          if (pending) {
            const hasActiveModal = () => {
              const el = document.querySelector(
                '.popup-overlay:not([style*="display: none"]):not([style*="display:none"]), .file-info-modal-overlay.show, [role="dialog"].show, .modal.show'
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

    showFeatureMenu(guides, title = 'Features on this Page', subtitle = 'Select a feature to explore its interactive guide, or skip.') {
      this.cleanup();
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
      guides.forEach((g, idx) => {
        const name = g.name || g.steps?.[0]?.title || g.id;
        const count = g.steps?.length || 0;
        const aimText = g.aim ? `<p style="color:#a5b4fc; font-weight:500; margin-bottom:2px;">🎯 ${g.aim}</p>` : '';
        const isCompleted = g.status === 'completed';
        const isDismissed = g.status === 'dismissed';
        const badge = isCompleted ? ' <span style="color:#10b981;font-size:11px;">(Completed)</span>' : '';

        itemsHtml += `
          <li class="guide-menu-item" style="${isDismissed ? 'opacity:0.4;' : ''}">
            <div class="guide-menu-info">
              <h5>${name}${badge}</h5>
              ${aimText}
              <p>${count} interactive ${count === 1 ? 'step' : 'steps'}</p>
            </div>
            <div class="guide-menu-actions">
              <button class="guide-btn guide-btn-skip btn-guide-skip" data-id="${g.id}">Skip</button>
              <button class="guide-btn guide-btn-next btn-guide-start" data-idx="${idx}">${isCompleted ? 'Replay' : 'Start'}</button>
            </div>
          </li>
        `;
      });

      card.innerHTML = `
        <div class="guide-menu-header">
          <h3 id="guide-menu-title">${title}</h3>
          <button class="guide-menu-close" id="guide-menu-close" aria-label="Close guides menu">&times;</button>
        </div>
        <p class="guide-menu-desc">${subtitle}</p>
        <ul class="guide-menu-list">${itemsHtml}</ul>
        <div style="display:flex; justify-content:flex-end;">
          <button class="guide-btn guide-btn-skip" id="guide-menu-dismiss-all">Close</button>
        </div>
      `;

      document.body.appendChild(card);
      this._attachEscape();

      // Focus trap and initial focus
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
          const selected = guides[idx];
          this.cleanup();
          this.startGuide(selected);
        });
      });

      card.querySelectorAll('.btn-guide-skip').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          const gid = e.currentTarget.getAttribute('data-id');
          await this.syncProgressDirect(gid, 'dismissed', 0, 1);
          const guideObj = guides.find(x => x.id === gid);
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
      const r = 8;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      // SVG path cutout with rounded rectangle hole
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

      // Wait until smooth scrolling settles before capturing rects
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

      // Start check with initial raf
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
      const aimBadge = this.currentGuide?.aim ? `<div class="guide-aim-badge">🎯 Aim: ${this.currentGuide.aim}</div>` : '';
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
      const tooltipW = tooltip.offsetWidth || 300;
      const margin = 12;

      // Position: fixed uses viewport coordinates directly
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
      // After finishing one guide, re-open feature menu to let user take another guide
      if (this.allScreenGuides && this.allScreenGuides.length > 1) {
        this.showFeatureMenu(
          this.allScreenGuides,
          'Guide Finished! 🎉',
          'Explore another feature on this page or tap Close.'
        );
      }
    }

    dismiss() {
      this.syncProgress('dismissed', this.currentStepIdx);
      if (this.currentGuide) {
        this.currentGuide.status = 'dismissed';
      }
      this.cleanup();
      // On skip/dismiss, offer other page guides
      if (this.allScreenGuides && this.allScreenGuides.length > 1) {
        this.showFeatureMenu(
          this.allScreenGuides,
          'Features on this Page',
          'Choose another feature to explore, or tap Close.'
        );
      }
    }

    openMenu() {
      if (this.allScreenGuides && this.allScreenGuides.length > 0) {
        this.showFeatureMenu(this.allScreenGuides);
      } else {
        this.init(this.screenName);
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
