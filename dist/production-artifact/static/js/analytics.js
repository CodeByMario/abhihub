/**
 * AbhiHub Analytics Engine v2.0
 * Zero-PII, canonical taxonomy, environment-isolated telemetry client.
 */
(function (window, document) {
  'use strict';

  var CONSENT_KEY = 'abhihub-consent';
  var GA_MEASUREMENT_ID = 'G-EH5BGS9BEG';
  var PII_REGEX = /[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+/;

  // Detect local / testing environment
  var isLocalEnv = /^(localhost|127\.0\.0\.1|0\.0\.0\.0|.*\.local)$/.test(window.location.hostname);
  var isTestMode = Boolean(window.__ABHIHUB_TEST_MODE__);

  // Ephemeral session identifier
  var sessionId = sessionStorage.getItem('abhihub_session_id');
  if (!sessionId) {
    sessionId = 's_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    try { sessionStorage.setItem('abhihub_session_id', sessionId); } catch (e) {}
  }

  // Active user context (Zero PII)
  var currentUserContext = {
    userId: 'anonymous',
    userType: 'anonymous',
    userRole: 'anonymous',
    userCollege: '',
    userBranch: '',
    userYearOfStudy: '',
    creatorStatus: 'never_uploaded',
    readerStatus: 'never_read',
    engagementStage: 'new'
  };

  function hasConsent() {
    try {
      return localStorage.getItem(CONSENT_KEY) === 'granted';
    } catch (e) {
      return false;
    }
  }

  function sanitizeValue(val) {
    if (val === null || val === undefined) return '';
    if (typeof val === 'string') {
      // Strip any accidental email strings
      if (PII_REGEX.test(val)) return '[REDACTED_EMAIL]';
      return val.slice(0, 300);
    }
    return val;
  }

  function sanitizePayload(params) {
    var clean = {};
    if (!params || typeof params !== 'object') return clean;
    var keys = Object.keys(params);
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      // Explicitly block PII keys
      if (/email|name|phone|mobile|password|token|secret/i.test(k) && k !== 'file_name' && k !== 'feature_name' && k !== 'filter_name') {
        continue;
      }
      clean[k] = sanitizeValue(params[k]);
    }
    return clean;
  }

  var AbhiHubAnalytics = {
    sessionId: sessionId,
    isLocal: isLocalEnv,

    isAllowed: function () {
      return hasConsent() && !window.__ABHIHUB_ANALYTICS_DISABLED__;
    },

    setUser: function (context) {
      if (!context) return;
      currentUserContext.userId = context.userId || context.uid || 'anonymous';
      currentUserContext.userType = (currentUserContext.userId && currentUserContext.userId !== 'anonymous') ? 'authenticated' : 'anonymous';
      currentUserContext.userRole = context.role || 'anonymous';
      currentUserContext.userCollege = sanitizeValue(context.college || '');
      currentUserContext.userBranch = sanitizeValue(context.branch || '');
      currentUserContext.userYearOfStudy = sanitizeValue(context.yearOfStudy || context.year_of_study || '');
      currentUserContext.creatorStatus = context.creatorStatus || currentUserContext.creatorStatus;
      currentUserContext.readerStatus = context.readerStatus || currentUserContext.readerStatus;
      currentUserContext.engagementStage = context.engagementStage || currentUserContext.engagementStage;

      if (window.gtag && this.isAllowed() && !isLocalEnv) {
        window.gtag('set', 'user_properties', {
          user_id: currentUserContext.userId,
          user_type: currentUserContext.userType,
          user_role: currentUserContext.userRole,
          user_college: currentUserContext.userCollege,
          user_branch: currentUserContext.userBranch,
          user_year_of_study: currentUserContext.userYearOfStudy,
          creator_status: currentUserContext.creatorStatus,
          reader_status: currentUserContext.readerStatus,
          engagement_stage: currentUserContext.engagementStage
        });
      }
    },

    clearUser: function () {
      currentUserContext = {
        userId: 'anonymous',
        userType: 'anonymous',
        userRole: 'anonymous',
        userCollege: '',
        userBranch: '',
        userYearOfStudy: '',
        creatorStatus: 'never_uploaded',
        readerStatus: 'never_read',
        engagementStage: 'new'
      };
      if (window.gtag && this.isAllowed() && !isLocalEnv) {
        window.gtag('set', 'user_properties', {
          user_id: 'anonymous',
          user_type: 'anonymous',
          user_role: 'anonymous'
        });
      }
    },

    track: function (eventName, properties) {
      var cleanProps = sanitizePayload(properties);
      cleanProps.session_id = sessionId;
      cleanProps.platform = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ? 'mobile' : 'desktop';
      cleanProps.timestamp = new Date().toISOString();

      if (isTestMode || window.__ABHIHUB_EVENT_LOG__) {
        window.__ABHIHUB_EVENT_LOG__ = window.__ABHIHUB_EVENT_LOG__ || [];
        window.__ABHIHUB_EVENT_LOG__.push({ event: eventName, params: cleanProps });
      }

      if (isLocalEnv) {
        console.debug('[Analytics-Dev]', eventName, cleanProps);
        return;
      }

      if (!this.isAllowed()) return;

      if (typeof window.gtag === 'function') {
        window.gtag('event', eventName, cleanProps);
      }
    },

    trackError: function (errorContext) {
      var clean = sanitizePayload(errorContext);
      this.track('client_error', {
        error_code: clean.error_code || clean.error_type || 'UNKNOWN_ERROR',
        surface: clean.surface || clean.page_path || window.location.pathname,
        recoverable: clean.recoverable !== false
      });
    }
  };

  // Expose canonical instance
  window.AbhiHubAnalytics = AbhiHubAnalytics;

  // Backward-compatibility bridge for legacy AbhiHubTracking calls
  window.AbhiHubTracking = {
    trackFileView: function (fileName, fileType, fileId, subject, college, branch, year) {
      AbhiHubAnalytics.track('content_viewed', {
        content_type: fileType || 'notes',
        content_id: fileId || fileName || '',
        category: subject || 'general',
        branch: branch || '',
        academic_year: year || ''
      });
    },

    trackFileClose: function () {
      // no-op, replaced by threshold engagement
    },

    trackFileDownload: function (fileName, fileType, fileId, subject) {
      AbhiHubAnalytics.track('content_engaged', {
        content_type: fileType || 'notes',
        content_id: fileId || fileName || '',
        engagement_type: 'download',
        category: subject || 'general'
      });
    },

    trackSearch: function (searchQuery, resultCount, searchType) {
      AbhiHubAnalytics.track('search_submitted', {
        search_area: searchType || 'global',
        result_count: resultCount || 0,
        query_length: (searchQuery || '').length
      });
    },

    trackLogin: function (loginMethod) {
      AbhiHubAnalytics.track('login', {
        method: loginMethod || 'email'
      });
    },

    trackSignup: function (signupMethod) {
      AbhiHubAnalytics.track('sign_up', {
        method: signupMethod || 'email'
      });
    },

    trackLogout: function () {
      AbhiHubAnalytics.track('logout', {});
    },

    trackShare: function (shareMethod, contentType, contentName) {
      AbhiHubAnalytics.track('content_engaged', {
        content_type: contentType || 'notes',
        engagement_type: 'share',
        share_channel: shareMethod || 'unknown'
      });
    },

    trackUploadStarted: function (count, method, category) {
      AbhiHubAnalytics.track('upload_started', {
        content_type: category || 'notes',
        method: method || 'file_picker',
        file_count: count || 1
      });
    },

    trackUploadCompleted: function (count, method, types, totalSizeKb) {
      var sizeBucket = (totalSizeKb < 1024) ? 'small_<1mb' : (totalSizeKb < 5120 ? 'medium_1-5mb' : 'large_>5mb');
      AbhiHubAnalytics.track('upload_completed', {
        content_type: types || 'notes',
        file_type: types || 'pdf',
        file_size_bucket: sizeBucket,
        file_count: count || 1
      });
    },

    trackUploadFailed: function (reason, errorType, method) {
      AbhiHubAnalytics.track('upload_failed', {
        failure_code: reason || errorType || 'unknown_error',
        stage: method || 'network_transfer'
      });
    },

    trackUploadAbandoned: function (stage) {
      AbhiHubAnalytics.track('upload_abandoned', {
        stage: stage || 'file_selected'
      });
    },

    trackFeatureUsage: function (featureName) {
      AbhiHubAnalytics.track('feature_viewed', {
        feature_name: featureName || 'unknown'
      });
    },

    trackError: function (errorType, errorMessage, severity, pagePath) {
      AbhiHubAnalytics.track('client_error', {
        error_code: errorType || 'GENERIC_ERROR',
        surface: pagePath || window.location.pathname,
        recoverable: severity !== 'critical'
      });
    },

    trackEvent: function (eventName, params) {
      AbhiHubAnalytics.track(eventName, params);
    },

    trackDownload: function (fileName, fileType, subject) {
      this.trackFileDownload(fileName, fileType, '', subject);
    }
  };

})(window, document);
