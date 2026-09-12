/**
 * ABHIHUB ANALYTICS INTEGRATION HELPER v2.0
 * Automatically wires UI interaction hooks to AbhiHubAnalytics.
 */

(function () {
  'use strict';

  function getTracker() {
    return window.AbhiHubAnalytics || window.AbhiHubTracking;
  }

  // ==========================================
  // AUTO-TRACK FILE CARD CLICKS
  // ==========================================
  function setupFileCardTracking() {
    document.addEventListener('click', function (e) {
      const fileCard = e.target.closest('.file-card, [data-file-card]');
      if (fileCard) {
        const tracker = getTracker();
        if (!tracker) return;

        const fileName = fileCard.querySelector('.file-card-title')?.textContent?.trim() || 'unknown';
        const subject = fileCard.querySelector('[data-subject]')?.textContent?.trim() || 'unknown';
        const fileType = fileCard.dataset.fileType || 'notes';
        const fileId = fileCard.dataset.fileId || fileCard.dataset.documentId || '';

        if (window.AbhiHubAnalytics) {
          window.AbhiHubAnalytics.track('content_viewed', {
            content_type: fileType,
            content_id: fileId || fileName,
            category: subject
          });
        } else if (tracker.trackFileView) {
          tracker.trackFileView(fileName, fileType, fileId, subject);
        }
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
        const tracker = getTracker();
        if (!tracker) return;

        const fileName = downloadBtn.dataset.fileName || downloadBtn.textContent?.trim() || 'unknown';
        const fileType = downloadBtn.dataset.fileType || 'notes';
        const subject = downloadBtn.dataset.subject || 'unknown';
        const fileId = downloadBtn.dataset.fileId || downloadBtn.dataset.documentId || '';

        if (window.AbhiHubAnalytics) {
          window.AbhiHubAnalytics.track('content_engaged', {
            content_type: fileType,
            content_id: fileId || fileName,
            engagement_type: 'download',
            category: subject
          });
        } else if (tracker.trackFileDownload) {
          tracker.trackFileDownload(fileName, fileType, fileId, subject);
        }
      }
    });
  }

  // ==========================================
  // AUTO-TRACK SEARCH SUBMISSIONS (ZERO RAW TEXT)
  // ==========================================
  function setupSearchTracking() {
    const searchForms = document.querySelectorAll('form[data-search-form], .search-form, [role="search"]');

    searchForms.forEach(form => {
      form.addEventListener('submit', function (e) {
        const tracker = getTracker();
        if (!tracker) return;

        const searchInput = form.querySelector('input[type="text"], input[name="q"], input[name="search"]');
        if (searchInput && searchInput.value.trim()) {
          const queryVal = searchInput.value.trim();
          const searchArea = form.dataset.searchType || 'global';
          const resultCount = document.querySelectorAll('[data-search-result]').length;

          if (window.AbhiHubAnalytics) {
            window.AbhiHubAnalytics.track('search_submitted', {
              search_area: searchArea,
              result_count: resultCount,
              query_length: queryVal.length
            });
            if (resultCount === 0) {
              window.AbhiHubAnalytics.track('empty_state_viewed', {
                surface: 'search',
                reason_code: 'no_results_found'
              });
            }
          } else if (tracker.trackSearch) {
            tracker.trackSearch(queryVal, resultCount, searchArea);
          }
        }
      });
    });
  }

  // ==========================================
  // AUTO-TRACK FILTER ACTIONS
  // ==========================================
  function setupFilterTracking() {
    document.addEventListener('change', function (e) {
      const filterElement = e.target.closest('.dropdown, select[data-filter], [data-filter-select]');
      if (filterElement) {
        const tracker = getTracker();
        if (!tracker) return;

        const filterType = filterElement.dataset.filterType || filterElement.name || 'filter';
        const filterArea = filterElement.dataset.filterArea || 'resource_list';
        const resultSelector = filterElement.dataset.resultSelector || '[data-search-result]';
        const resultCount = document.querySelectorAll(resultSelector + ':not(.hidden)').length;

        if (window.AbhiHubAnalytics) {
          window.AbhiHubAnalytics.track('filter_applied', {
            area: filterArea,
            filter_name: filterType,
            result_count: resultCount
          });
        }
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
        const tracker = getTracker();
        if (!tracker) return;

        const shareMethod = shareBtn.dataset.shareMethod || 'copy_link';
        const contentType = shareBtn.dataset.contentType || 'notes';

        if (window.AbhiHubAnalytics) {
          window.AbhiHubAnalytics.track('content_engaged', {
            content_type: contentType,
            engagement_type: 'share',
            share_channel: shareMethod
          });
        } else if (tracker.trackShare) {
          tracker.trackShare(shareMethod, contentType, '');
        }
      }
    });
  }

  // ==========================================
  // GLOBAL ERROR TRACKING
  // ==========================================
  window.addEventListener('error', function (e) {
    const tracker = getTracker();
    if (tracker && tracker.trackError) {
      tracker.trackError({
        error_code: 'JS_UNHANDLED_EXCEPTION',
        surface: window.location.pathname,
        recoverable: true
      });
    }
  });

  // ==========================================
  // INITIALIZE
  // ==========================================
  function initializeTracking() {
    setupFileCardTracking();
    setupDownloadTracking();
    setupSearchTracking();
    setupFilterTracking();
    setupShareTracking();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeTracking);
  } else {
    initializeTracking();
  }

})();
