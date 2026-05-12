# Google Analytics 4 (GA4) Tracking

## Overview
GA4 tracking is implemented via `templates/google_tag.html` and auto-wired through `static/js/analytics-helper.js`.

**Measurement ID:** `G-EH5BGS9BEG`

## Architecture

### Include Chain
- `templates/p_struct.html` (line 601) → `{% include 'google_tag.html' %}`
- All pages that extend `p_struct.html` automatically get GA tracking
- Standalone pages (`about.html`, `terms.html`, `privacy.html`, `forgot_password.html`, `p_error.html`, `team.html`, `upload.html`) include `google_tag.html` directly

> **IMPORTANT:** Pages extending `p_struct.html` must NOT also `{% include 'google_tag.html' %}` — this causes **double initialization**, inflating pageviews. This was fixed in `p_login.html` and `p_signup.html` (May 2026).

### Global Object: `window.AbhiHubTracking`
Defined in `google_tag.html`, exposes all tracking methods. Used by:
- `static/js/analytics-helper.js` — auto-wires DOM events (clicks, forms, scrolls)
- `static/login-auth.js` — login/signup/logout events

### User Identification
```javascript
// Cross-device tracking via user_id (from session['user']['uid'])
gtag('config', 'G-EH5BGS9BEG', { 'user_id': '...' });
gtag('set', { 'user_id': '...' });
```

### User Properties Sent
| Property | Source | Description |
|----------|--------|-------------|
| `user_type` | Jinja `session` | `authenticated` or `anonymous` |
| `user_name` | `session.user.name` | Display name |
| `user_email` | `session.user.email` | Email address |
| `login_provider` | `session.user.provider` | `google`, `email`, etc. |
| `platform` | JS `navigator.userAgent` | `mobile` or `desktop` |
| `app_version` | Flask `app_version` | Defaults to `1.0.0` |

## Tracked Events

### Core Events (in `google_tag.html`)
| Event | Function | Trigger |
|-------|----------|---------|
| `page_view` | `trackPageView()` | Every page load |
| `file_view` + `view_item` | `trackFileView()` | File card click |
| `file_download` + `select_content` | `trackFileDownload()` | Download button |
| `search` | `trackSearch()` | Search form submit |
| `subject_access` | `trackSubjectAccess()` | Subject card click |
| `login` | `trackLogin()` | Successful login |
| `sign_up` | `trackSignup()` | Successful signup |
| `logout` | `trackLogout()` | User logs out |
| `file_upload` | `trackUpload()` | File uploaded |
| `share` | `trackShare()` | Share button click |
| `filter_applied` | `trackFilterAction()` | Filter/sort change |
| `section_engagement` | `trackSectionEngagement()` | Section scroll into view |
| `element_click` | `trackElementClick()` | Tracked button clicks |
| `app_error` | `trackError()` | JS errors / zero results |
| `page_performance` | `trackPerformance()` | Page load timing |
| `form_submit` | `trackFormSubmission()` | Form submissions |
| `engagement_time` | `trackTimeOnPage()` | On `beforeunload` |
| `scroll_depth_50` | auto | 50% scroll reached |

### Funnel Events
| Funnel | Steps |
|--------|-------|
| Discovery → Download | `page_view` → `search_or_browse` → `file_view` → `file_download` |
| New User Activation | `first_visit` → `sign_up` → `first_file_view` → `first_download` |
| Premium Conversion | `premium_page_view` → `view_plans` → `start_checkout` → `complete_purchase` |

### Auto-Tracking (`analytics-helper.js`)
Auto-wires DOM events to tracking functions:
- File card clicks (`.file-card`, `[data-file-card]`)
- Download buttons (`.download-btn`, `[data-download]`)
- Search forms (`[data-search-form]`, `.search-form`, `[role="search"]`)
- Filter/sort dropdowns (`[data-filter-select]`)
- Subject links (`[data-subject-link]`)
- Share buttons (`[data-share]`)
- Premium buttons (`[data-premium-action]`)
- Tracked buttons (`[data-track]`)
- Section visibility (`[data-analytics-section]`)
- Global JS errors

## Auth Event Tracking (`login-auth.js`)
- **Email login success** → `trackLogin('email', email)`
- **Google OAuth success** → `trackLogin('google_oauth', '')`
- **Email signup success** → `trackSignup('email', email)`

## Session Management
Custom `session_id` stored in `sessionStorage`, generated via `getOrCreateSessionId()`.

## Bugs Fixed (May 2026)
1. **`getOrCreateSessionId()` missing `return`** — session_id was always `undefined`
2. **Duplicate GA include** in `p_login.html` and `p_signup.html` — double pageview counting
3. **`registration_date` in user properties** — `localStorage.getItem()` inline in Jinja caused evaluation issues; removed
4. **Session user references** — Fixed `session.user.id` → `session.get('user', {}).get('uid', '')`
5. **Login/signup tracking** — Added `AbhiHubTracking.trackLogin/trackSignup` calls to `login-auth.js`

## Files
- `templates/google_tag.html` — Core GA4 script, tracking methods, Schema.org markup
- `static/js/analytics-helper.js` — Auto-wiring DOM events to tracking
- `static/login-auth.js` — Auth flow with GA event calls
- `templates/p_struct.html` (line 601) — GA include in base template
