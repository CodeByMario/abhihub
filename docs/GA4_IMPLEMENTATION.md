# Google Analytics 4 (GA4) Implementation Guide

## Overview
AbhiHub uses Google Analytics 4 (GA4) with Measurement ID `G-EH5BGS9BEG` to track user behavior, file access patterns, and business metrics. This document describes the complete implementation.

## Architecture

### Components
| Component | File | Purpose |
|-----------|------|---------|
| GA4 Tag + Consent | `templates/google_tag.html` | Loads GA4 SDK, manages consent, sets user properties |
| Server-side Analytics | `methods/analytics_tracker.py` | API endpoints for server-side logging |
| Template Context | `app.py` context processor | Injects user profile data into all templates |
| Auto-tracking | `static/js/analytics-helper.js` | Automatic UI interaction tracking |
| Manual tracking | `static/js/inline-handler-compat.js`, etc. | Custom event tracking for specific features |

### Data Flow
```
User loads page
    ↓
google_tag.html renders with user_profile_json from server
    ↓
GA4 SDK loads (after consent)
    ↓
User properties set: email, name, mobile, college, branch, year
    ↓
Page view event sent with full context
    ↓
Client interactions tracked via AbhiHubTracking API
    ↓
Server-side endpoints log backup copies to Supabase
```

## User Profile Data

### What's Tracked
The following user data is sent to GA4 as **user_properties**:

| Property | Source | Example |
|----------|--------|---------|
| `user_type` | Session auth status | "authenticated" / "anonymous" |
| `user_email` | Supabase Auth | "user@example.com" |
| `user_name` | Supabase user_metadata | "John Doe" |
| `user_mobile` | students table | "9876543210" |
| `user_college` | students → colleges table | "G.H. Raisoni College of Engineering" |
| `user_branch` | students → departments table | "Computer Science" |
| `user_year_of_study` | students.pursuing_year | "3" |
| `user_role` | Auth provider | "email" / "google" |
| `platform` | User agent detection | "mobile" / "desktop" |
| `session_id` | Generated client-side | "session_123..." |

### How It's Collected
1. User logs in via Supabase Auth → session['user'] populated
2. Server renders template with `get_full_profile_json()` 
3. Profile includes: uid, email, name, mobile, college, branch, year, role
4. Data embedded in `window.ABHIHUB_USER_PROFILE` JS variable
5. GA4 `gtag('set', { user_properties: {...} })` sends on page load

## Events Tracked

### Automatic Events (via google_tag.html)
| Event | Trigger | Key Parameters |
|-------|---------|----------------|
| `page_view` | Every page load | page_path, page_title, user properties, session metrics |
| `session_start_custom` | First page load when logged in | user_id, email, college, branch |
| `page_performance` | Page load complete | load_time_ms, dom_content_loaded_ms, TTFB |
| `session_end` | Page unload / tab hide | session_duration, page_views, file_views, engagement_quality |

### File Interaction Events
| Event | Trigger | Key Parameters |
|-------|---------|----------------|
| `file_view` | File opened (throttled 2s) | file_name, file_type, document_id, subject, college, branch, year, user info, time_spent_seconds |
| `file_download` | Download clicked | file_name, file_type, document_id, subject, college, branch |
| `view_item` (GA4 Ecommerce) | File viewed | items: [{item_id, item_name, item_category, ...}] |
| `select_content` (GA4 Ecommerce) | Download clicked | content_type: 'file', items: [...] |

### Search & Navigation Events
| Event | Trigger | Key Parameters |
|-------|---------|----------------|
| `search` | Search submitted | search_term, search_type, result_count, zero_results |
| `subject_access` | Subject clicked | subject_name, content_type, college, branch |
| `filter_applied` | Filter changed | filter_type, filter_value, result_count |

### User Lifecycle Events
| Event | Trigger | Key Parameters |
|-------|---------|----------------|
| `login` | User logs in | method, user_id, user_email, user_name |
| `sign_up` | New user registers | method, user_id, user_email, user_name |
| `logout` | User logs out | user_id, session_duration_seconds |

### Engagement Events
| Event | Trigger | Key Parameters |
|-------|---------|----------------|
| `element_click` | Tracked button clicked | element_name, element_type, action_value |
| `section_engagement` | Section viewed (IntersectionObserver) | section_name, scroll_depth |
| `feature_usage` | Feature interacted | feature_name, feature_status, experience_rating |
| `share` | Share button clicked | method, content_type, content_name |
| `notification_open` | Notification panel opened | unread_count |

### Upload Events (via inline-handler-compat.js)
| Event | Trigger | Key Parameters |
|-------|---------|----------------|
| `upload_started` | Upload begins | count, method, category |
| `upload_completed` | Upload succeeds | count, method, types, total_size_kb, user info |
| `upload_failed` | Upload fails | reason, error_type, method |
| `upload_abandoned` | Upload cancelled | stage (uploading/metadata) |
| `camera_upload` | Camera upload used | - |
| `xp_earned` | Reputation earned | xp, score, count |
| `badge_unlocked` | Badge earned | badge name |

### Error Events
| Event | Trigger | Key Parameters |
|-------|---------|----------------|
| `app_error` | JS error / tracked error | error_type, error_message, severity, user_id, page_path, session_duration |
| `javascript_error` | Window error event | error message, severity: 'error' |

### Other Events
| Event | Trigger | Key Parameters |
|-------|---------|----------------|
| `premium_interaction` | Premium feature used | action, plan_type |
| `form_submit` | Form submitted | form_name, form_data |
| `engagement_time` | Periodic + on unload | time_on_site_seconds, session_page_views |
| `api_latency` | API call completed | endpoint, latency_ms, status_code |
| `study_pass_*` | Study pass interactions | various |

## Session Tracking

### Session ID
- Generated on first page load: `session_${Date.now()}_${random}`
- Stored in `sessionStorage` as `ga_session_id`
- Persists across page navigations within the tab
- Sent with every event

### Session Duration
- Start time: `window.ABHIHUB_SESSION_START = Date.now()`
- End detected via:
  - `beforeunload` event (tab closing)
  - `visibilitychange` to 'hidden' (tab switch)
- Duration sent as `session_duration_seconds` in `session_end` event

### Engagement Quality Score
Calculated on session end:
```
score = min(
    (duration_minutes / 10 * 30),     // up to 30 for 10+ min
    (page_views * 10),                 // up to 30 for 3+ pages
    (file_views * 10),                 // up to 20 for 2+ files
    (downloads > 0 ? 10 : 0),         // 10 for download
    (searches > 0 ? 10 : 0)           // 10 for search
)
quality = 'high' if score >= 75
          'medium' if score >= 40
          'low' otherwise
```

## File Access Duration Tracking

### How It Works
1. When file view begins: `trackFileOpen()` records open time
2. `window.ABHIHUB_CURRENT_FILE` stores file metadata
3. When file closed/navigated away: `trackFileClose()` calculates duration
4. `time_spent_seconds` sent with `file_view` event
5. Server endpoint `/api/analytics/file-access` logs to Supabase

### Usage in Templates
```javascript
// When PDF reader opens:
window.AbhiHubTracking.trackFileView(
    fileName,      // e.g. "DBMS_Notes.pdf"
    fileType,      // e.g. "pdf"
    documentId,    // e.g. "abc-123-uuid"
    subject,       // e.g. "DBMS"
    college,       // e.g. "G.H. Raisoni"
    branch,        // e.g. "Computer Science"
    year           // e.g. "3"
);

// When PDF reader closes/navigates away:
window.AbhiHubTracking.trackFileClose();
```

## Server-Side Analytics Endpoints

### POST /api/analytics/pageview
Logs pageview to server + Supabase backup.
```json
Request: {
  "page_path": "/resource/...",
  "page_title": "Document Title",
  "page_location": "https://...",
  "page_category": "resource",
  "referrer": "https://...",
  "session_id": "session_..."
}
Response: { "success": true }
```

### GET /api/analytics/user-properties
Returns current user's profile data for client-side GA4 update.
```json
Response: {
  "success": true,
  "userProperties": {
    "userId": "abc-123",
    "email": "user@example.com",
    "name": "John Doe",
    "mobile": "9876543210",
    "branch": "Computer Science",
    "college": "G.H. Raisoni",
    "yearOfStudy": "3",
    "role": "email",
    "isAuthenticated": true
  }
}
```

### POST /api/analytics/error
Logs error to server + Supabase.
```json
Request: {
  "error_type": "javascript_error",
  "error_message": "Something broke",
  "severity": "error",
  "page_path": "/resource/...",
  "stack_trace": "..."
}
Response: { "success": true }
```

### POST /api/analytics/file-access
Logs file access with duration to server + Supabase.
```json
Request: {
  "document_id": "abc-123",
  "file_name": "DBMS_Notes.pdf",
  "file_type": "pdf",
  "subject": "DBMS",
  "college": "G.H. Raisoni",
  "branch": "Computer Science",
  "year": "3",
  "time_spent_seconds": 125,
  "action": "view",
  "session_id": "session_..."
}
Response: { "success": true }
```

### POST /api/analytics/session-end
Logs session end with summary metrics.
```json
Request: {
  "session_id": "session_...",
  "session_duration_seconds": 300,
  "page_views": 5,
  "file_views": 3,
  "downloads": 1,
  "searches": 2,
  "engagement_quality": "high",
  "exit_page": "/resource/..."
}
Response: { "success": true }
```

## How to Use in New Features

### Track a New Event
```javascript
if (window.AbhiHubTracking) {
    window.AbhiHubTracking.trackEvent('my_custom_event', {
        param1: 'value1',
        param2: 'value2'
    });
}
```

### Track File Access (for new file viewers)
```javascript
// On file open
window.AbhiHubTracking.trackFileView(
    'filename.pdf',    // file name
    'pdf',             // file type
    'doc-uuid',        // document ID
    'Subject',         // subject
    'College',         // college
    'Branch',          // branch
    '3'                // year of study
);

// On file close
window.AbhiHubTracking.trackFileClose();
```

### Update User Properties (after profile change)
```javascript
fetch('/api/analytics/user-properties')
    .then(r => r.json())
    .then(data => {
        if (data.success && window.gtag) {
            window.gtag('set', { user_id: data.userProperties.userId });
            window.gtag('set', {
                user_properties: data.userProperties
            });
        }
    });
```

## GA4 Custom Dimensions (for Exploration Reports)

These are sent as event parameters and can be registered as custom dimensions in GA4:

| Parameter | Description | Event Scope |
|-----------|-------------|-------------|
| `user_email` | User's email | user |
| `user_name` | User's full name | user |
| `user_mobile` | Mobile number | user |
| `user_college` | College name | user |
| `user_branch` | Branch/department | user |
| `user_year_of_study` | Current year | user |
| `session_id` | Unique session ID | event |
| `time_spent_seconds` | Time on file | event |
| `engagement_quality` | Session quality (high/medium/low) | event |
| `session_duration_seconds` | Total session time | event |
| `file_size_bucket` | File size category | event |
| `user_cohort` | Weeks since registration | event |
| `session_quality_score` | Numeric quality score 0-100 | event |

## Consent Management

- Consent stored in `localStorage` key `abhihub-consent`
- Values: `'granted'` or `'denied'`
- Consent banner shown on first visit
- When consent denied: `window.__ABHIHUB_ANALYTICS_DISABLED__ = true`
- GA4 consent mode: `analytics_storage: 'granted'` when accepted

## Privacy & Compliance

- IP anonymization enabled: `anonymize_ip: true`
- Google signals disabled: `allow_google_signals: false`
- Ad personalization disabled: `allow_ad_personalization_signals: false`
- Consent mode implemented per IAB TCF guidelines
- User can decline analytics at any time

## Troubleshooting

### Events Not Showing in GA4
1. Check consent: `localStorage.getItem('abhihub-consent')` should be `'granted'`
2. Check GA4 SDK loaded: `typeof window.gtag === 'function'`
3. Check network tab: requests to `google-analytics.com` and `analytics.google.com`
4. Real-time reports show events within minutes

### User Properties Not Updating
1. Verify `window.ABHIHUB_USER_PROFILE` is populated
2. Check server response from `/api/analytics/user-properties`
3. Profile data requires logged-in user with college/branch set

### Server Logs Not Appearing
1. Check Flask logs for `[Analytics]` prefixed messages
2. Verify Supabase client connectivity
3. Check `/api/analytics/*` endpoints return 200

## Files Modified (2026-08-17)

| File | Change |
|------|--------|
| `app.py` | Added analytics route registration + context processor |
| `methods/analytics_tracker.py` | New file: server-side analytics API |
| `templates/google_tag.html` | Enhanced: full user properties, session tracking, file stay time |
| `templates/p_struct.html` | Pass user_profile_json to google_tag |
| `templates/privacy.html` | Pass user_profile_json to google_tag |
| `templates/terms.html` | Pass user_profile_json to google_tag |
| `templates/about.html` | Pass user_profile_json to google_tag |
| `templates/team.html` | Pass user_profile_json to google_tag |
| `templates/forgot_password.html` | Pass user_profile_json to google_tag |
| `templates/reset_password_form.html` | Pass user_profile_json to google_tag |
| `templates/p_error.html` | Pass user_profile_json to google_tag |
| `templates/know_me/*(4 files)` | Pass user_profile_json to google_tag |
| `ANALYTICS_CHANGES.md` | New file: change log |
| `docs/GA4_IMPLEMENTATION.md` | New file: this guide |
