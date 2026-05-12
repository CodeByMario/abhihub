/**
 * ABHIHUB ANALYTICS INTEGRATION HELPER
 * 
 * This file should be included in pages to automatically wire up analytics tracking
 * to common user interactions (clicks, form submissions, etc.)
 */

(function () {
  'use strict';

  // Wait for GA to be ready
  if (!window.AbhiHubTracking) {
    console.warn('[Analytics] AbhiHubTracking not loaded yet');
    return;
  }

  const Analytics = window.AbhiHubTracking;

  // ==========================================
  // AUTO-TRACK FILE CARD CLICKS
  // ==========================================
  function setupFileCardTracking() {
    document.addEventListener('click', function (e) {
      const fileCard = e.target.closest('.file-card, [data-file-card]');
      if (fileCard) {
        const fileName = fileCard.querySelector('.file-card-title')?.textContent || 'unknown';
        const subject = fileCard.querySelector('[data-subject]')?.textContent || 'unknown';
        const fileType = fileCard.dataset.fileType || 'unknown';

        Analytics.trackFileView(fileName, fileType, subject);
      }
    });
  }

  // ==========================================
  // AUTO-TRACK DOWNLOAD BUTTONS
  // ==========================================
  function setupDownloadTracking() {
    document.addEventListener('click', function (e) {
      const downloadBtn = e.target.closest('.download-btn, [data-download], a[href*="/download"]');
      if (downloadBtn) {
        const fileName = downloadBtn.dataset.fileName || downloadBtn.textContent || 'unknown';
        const fileType = downloadBtn.dataset.fileType || 'file';
        const subject = downloadBtn.dataset.subject || 'unknown';

        Analytics.trackFileDownload(fileName, fileType, subject);
      }
    });
  }

  // ==========================================
  // AUTO-TRACK SEARCH SUBMISSIONS (ENHANCED)
  // ==========================================
  let searchRefinementCount = 0;
  let lastSearchTerm = '';

  function setupSearchTracking() {
    const searchForms = document.querySelectorAll('form[data-search-form], .search-form, [role="search"]');

    searchForms.forEach(form => {
      form.addEventListener('submit', function (e) {
        const searchInput = form.querySelector('input[type="text"], input[name="q"], input[name="search"]');
        if (searchInput && searchInput.value.trim()) {
          const searchTerm = searchInput.value;
          const searchType = form.dataset.searchType || 'general';

          // Check if this is a search refinement
          if (lastSearchTerm && lastSearchTerm !== searchTerm) {
            searchRefinementCount++;
          } else if (!lastSearchTerm) {
            searchRefinementCount = 0;
          }
          lastSearchTerm = searchTerm;

          // Get result count if available
          const resultCount = document.querySelectorAll('[data-search-result]').length;

          // Track with refinement level
          Analytics.trackSearch(searchTerm, resultCount, searchType, searchRefinementCount);

          // If zero results, track separately
          if (resultCount === 0) {
            Analytics.trackError('zero_search_results', searchTerm, 'info');
          }
        }
      });
    });
  }

  // ==========================================
  // AUTO-TRACK FILTER/SORT ACTIONS (ENHANCED)
  // ==========================================
  let activeFilters = {};

  function setupFilterTracking() {
    document.addEventListener('change', function (e) {
      const filterElement = e.target.closest('.dropdown, select[data-filter], [data-filter-select]');
      if (filterElement) {
        const filterType = filterElement.dataset.filterType || filterElement.name || 'unknown';
        const filterValue = e.target.value;

        // Track active filters
        if (filterValue && filterValue !== 'all' && filterValue !== '') {
          activeFilters[filterType] = filterValue;
        } else {
          delete activeFilters[filterType];
        }

        // Count visible results
        const resultSelector = filterElement.dataset.resultSelector || '[data-search-result]';
        const resultCount = document.querySelectorAll(resultSelector + ':not(.hidden)').length;

        // Build filter combination string
        const filterCombination = Object.entries(activeFilters)
          .map(([key, value]) => `${key}:${value}`)
          .join(',');

        // Track with enhanced data
        Analytics.trackFilterAction(filterType, filterValue, resultCount);

        // Track filter combination if multiple filters active
        if (Object.keys(activeFilters).length > 1) {
          gtag('event', 'filter_combination', {
            'combination': filterCombination,
            'filter_count': Object.keys(activeFilters).length,
            'result_count': resultCount
          });
          console.log('[Analytics] Filter combination:', filterCombination);
        }
      }
    });
  }

  // ==========================================
  // AUTO-TRACK SUBJECT NAVIGATION
  // ==========================================
  function setupSubjectTracking() {
    document.addEventListener('click', function (e) {
      const subjectLink = e.target.closest('[data-subject-link], .subject-card, .subject-btn');
      if (subjectLink) {
        const subjectName = subjectLink.dataset.subjectName || subjectLink.textContent || 'unknown';
        const contentType = subjectLink.dataset.contentType || 'notes';

        Analytics.trackSubjectAccess(subjectName, contentType);
      }
    });
  }

  // ==========================================
  // AUTO-TRACK SHARE BUTTONS
  // ==========================================
  function setupShareTracking() {
    document.addEventListener('click', function (e) {
      const shareBtn = e.target.closest('.share-btn, [data-share], button[data-share-method]');
      if (shareBtn) {
        const shareMethod = shareBtn.dataset.shareMethod || shareBtn.className || 'unknown';
        const contentName = shareBtn.dataset.contentName || document.title;
        const contentType = shareBtn.dataset.contentType || 'file';

        Analytics.trackShare(shareMethod, contentType, contentName);
      }
    });
  }

  // ==========================================
  // AUTO-TRACK PREMIUM ACTIONS
  // ==========================================
  function setupPremiumTracking() {
    document.addEventListener('click', function (e) {
      const premiumBtn = e.target.closest('[data-premium-action], .premium-btn, .upgrade-btn');
      if (premiumBtn) {
        const action = premiumBtn.dataset.premiumAction || 'click';
        const planType = premiumBtn.dataset.planType || 'basic';

        Analytics.trackPremiumInteraction(action, planType);
      }
    });
  }

  // ==========================================
  // AUTO-TRACK FORM SUBMISSIONS
  // ==========================================
  function setupFormTracking() {
    document.addEventListener('submit', function (e) {
      const form = e.target;
      if (form.dataset.trackingForm || form.className.includes('tracked-form')) {
        const formName = form.name || form.id || form.dataset.formName || 'unnamed_form';
        const formData = new FormData(form);
        const dataObj = Object.fromEntries(formData.entries());

        Analytics.trackFormSubmission(formName, dataObj);
      }
    });
  }

  // ==========================================
  // EXPOSE SECTION ENGAGEMENT TRACKER
  // ==========================================
  function setupIntersectionObserver() {
    if ('IntersectionObserver' in window) {
      const sections = document.querySelectorAll('[data-analytics-section]');

      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const sectionName = entry.target.dataset.analyticsSection;
            const engagementType = 'view';

            Analytics.trackSectionEngagement(sectionName, engagementType);

            // Unobserve after first view to avoid duplicate tracking
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0.5 });

      sections.forEach(section => observer.observe(section));
    }
  }

  // ==========================================
  // TRACK IMPORTANT BUTTON CLICKS
  // ==========================================
  function setupButtonTracking() {
    document.addEventListener('click', function (e) {
      const btn = e.target.closest('button[data-track], a[data-track]');
      if (btn) {
        const elementName = btn.dataset.track || btn.textContent || 'unknown';
        const elementType = btn.tagName.toLowerCase();
        const actionValue = btn.dataset.trackValue || 'click';

        Analytics.trackElementClick(elementName, elementType, actionValue);
      }
    });
  }

  // ==========================================
  // GLOBAL ERROR TRACKING
  // ==========================================
  window.addEventListener('error', function (e) {
    Analytics.trackError('javascript_error', e.message, 'error');
  });

  // ==========================================
  // INITIALIZE ALL TRACKING
  // ==========================================
  function initializeTracking() {
    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        setupFileCardTracking();
        setupDownloadTracking();
        setupSearchTracking();
        setupFilterTracking();
        setupSubjectTracking();
        setupShareTracking();
        setupPremiumTracking();
        setupFormTracking();
        setupIntersectionObserver();
        setupButtonTracking();

        console.log('[Analytics] All tracking handlers initialized');
      });
    } else {
      setupFileCardTracking();
      setupDownloadTracking();
      setupSearchTracking();
      setupFilterTracking();
      setupSubjectTracking();
      setupShareTracking();
      setupPremiumTracking();
      setupFormTracking();
      setupIntersectionObserver();
      setupButtonTracking();

      console.log('[Analytics] All tracking handlers initialized');
    }
  }

  // Start initialization
  initializeTracking();

})();
