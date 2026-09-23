/**
 * AbhiHub — Apple-Style Card Navigation & Perceived Performance Controller
 * Handles instant tap feedback (<50ms), top progress bar, double-click prevention,
 * BFCache history recovery, and slow network escalation.
 */

(function() {
  'use strict';

  let progressTimer = null;
  let slowNoticeTimer = null;
  let isNavigating = false;
  let currentCard = null;

  const AbhiHubTransition = {
    /**
     * Start the loading state when a card or link is triggered.
     * @param {HTMLElement} cardEl - The card element that was clicked.
     * @param {string} destinationUrl - The target URL.
     */
    start(cardEl, destinationUrl) {
      if (isNavigating) return false;
      isNavigating = true;
      currentCard = cardEl;

      // 1. Instant Card Micro-interaction (<50ms)
      if (cardEl) {
        cardEl.classList.add('is-navigating');
        cardEl.setAttribute('aria-busy', 'true');
      }

      // 2. Activate Full-Screen Branded Overlay (Option 1)
      const overlay = document.getElementById('abhihub-loading-overlay');
      if (overlay) {
        overlay.classList.add('is-visible');
      }

      // 3. Announce to Screen Readers
      const announcer = document.getElementById('abhihub-live-announcer');
      if (announcer) {
        announcer.textContent = 'Loading resource, please wait...';
      }

      // 4. Start Top Apple-Style Progress Bar
      const bar = document.getElementById('abhihub-progress-bar');
      if (bar) {
        bar.classList.remove('is-finishing');
        bar.classList.add('is-active');
        bar.style.width = '20%';

        // Smooth physics-like progress simulation
        let currentWidth = 20;
        clearInterval(progressTimer);
        progressTimer = setInterval(() => {
          if (currentWidth < 85) {
            currentWidth += (90 - currentWidth) * 0.12;
            bar.style.width = `${Math.min(currentWidth, 90)}%`;
          }
        }, 180);
      }

      // 5. Slow Network Escalation (>5.5 seconds)
      clearTimeout(slowNoticeTimer);
      slowNoticeTimer = setTimeout(() => {
        if (isNavigating) {
          const notice = document.getElementById('abhihub-nav-notice');
          if (notice) {
            notice.classList.add('is-visible');
          }
        }
      }, 5500);

      return true;
    },

    /**
     * Finish and dismiss the loading state once destination is ready.
     */
    finish() {
      clearInterval(progressTimer);
      clearTimeout(slowNoticeTimer);

      const overlay = document.getElementById('abhihub-loading-overlay');
      if (overlay) {
        overlay.classList.remove('is-visible');
      }

      const bar = document.getElementById('abhihub-progress-bar');
      if (bar) {
        bar.classList.add('is-finishing');
        setTimeout(() => {
          bar.classList.remove('is-active', 'is-finishing');
          bar.style.width = '0%';
        }, 400);
      }

      if (currentCard) {
        currentCard.classList.remove('is-navigating');
        currentCard.removeAttribute('aria-busy');
        currentCard = null;
      }

      const notice = document.getElementById('abhihub-nav-notice');
      if (notice) {
        notice.classList.remove('is-visible');
      }

      const announcer = document.getElementById('abhihub-live-announcer');
      if (announcer) {
        announcer.textContent = '';
      }

      isNavigating = false;
    },

    /**
     * Reset state completely (critical on BFCache back/forward navigation).
     */
    reset() {
      this.finish();
      document.querySelectorAll('.is-navigating').forEach(el => {
        el.classList.remove('is-navigating');
        el.removeAttribute('aria-busy');
      });
    }
  };

  window.AbhiHubTransition = AbhiHubTransition;

  // ── Global Event Delegation on Document ──
  document.addEventListener('click', function(e) {
    // Check if clicked element is inside a card link
    const card = e.target.closest('.pcard, [data-nav-card], .resource-card');
    if (!card) return;

    // Check if user clicked an explicit modal/info button inside the card (e.g. data-action="showFileInfo")
    const actionBtn = e.target.closest('[data-action], button, .file-info-icon');
    if (actionBtn && actionBtn !== card) {
      // Don't trigger page transition for modal triggers inside the card
      return;
    }

    const href = card.getAttribute('href') || (card.tagName === 'A' ? card.href : null);
    if (!href || href === '#' || href.startsWith('javascript:')) return;

    // Ignore middle-clicks, cmd/ctrl-clicks (opening in new tab)
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;

    // Prevent duplicate clicks if already navigating
    if (isNavigating) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }

    // Trigger instant transition
    AbhiHubTransition.start(card, href);
  }, false);

  // ── Dismiss on Page Load ──
  window.addEventListener('load', function() {
    AbhiHubTransition.finish();
  });

  // ── Dismiss on BFCache Restore (Back/Forward button in Safari & Chrome) ──
  window.addEventListener('pageshow', function(e) {
    if (e.persisted) {
      AbhiHubTransition.reset();
    }
  });

  // ── Dismiss if user leaves / navigates away or cancels ──
  window.addEventListener('pagehide', function() {
    clearTimeout(slowNoticeTimer);
    clearInterval(progressTimer);
  });
})();
