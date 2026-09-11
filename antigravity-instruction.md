# AbhiHub Analytics Redesign — Antigravity Instructions

## 1. Mission

Redesign AbhiHub analytics so measurement is accurate, privacy-conscious, debuggable, and useful for product decisions. Do not blindly add events. First inspect the existing application, analytics SDK/tag, authentication flow, database schema, routes, upload flow, profile, dashboard, storeroom, PYQs, notes, and deployment configuration.

Primary questions:

1. Which users upload notes and which only view/read them?
2. Which features attract users and produce meaningful engagement?
3. Which features frustrate, confuse, or cause abandonment/errors?
4. Is traffic authentic, duplicated, internal, test, or suspicious?
5. Where do users register, activate, return, upload, search, read, and leave?

## 2. Operating rules

- Use Ponytail coding rules.
- Use the Conductor workflow: inspect, plan, implement, test, review, document.
- Do not delete or rename existing analytics until a migration plan and compatibility mapping exist.
- Do not expose email addresses, names, note contents, tokens, passwords, or other personally identifiable information in analytics.
- Never send raw authentication IDs as publicly reportable analytics values. Use a stable, non-reversible pseudonymous user key only when necessary and permitted.
- Do not track keystrokes, full URLs containing secrets, private note text, or every scroll/click by default.
- Preserve application behavior while instrumenting it.
- Ask for clarification only when a decision cannot safely be inferred from the codebase.

## 3. Audit before coding

Create `docs/analytics/audit.md` containing:

- Current analytics provider, measurement ID, SDK/tag implementation, environment configuration, and loading conditions.
- Every existing event, trigger, parameter, user property, and page/screen identifier.
- Duplicate, incorrectly named, missing, or unreliable events.
- Authentication paths: Google login, email login, signup, logout, failed login, and account deletion if available.
- Main entities: user, note, PYQ, category, upload, bookmark/save, search, profile, storeroom, dashboard.
- Server-side events that must be authoritative rather than inferred from the browser.
- Consent, privacy, ad-blocker, offline, retry, and test-environment behavior.
- Current errors and data-quality risks.

Do not implement until the audit and proposed event map are written.

## 4. Measurement architecture

Create one analytics abstraction, for example:

```text
analytics.track(eventName, properties)
analytics.setUser(userContext)
analytics.clearUser()
analytics.trackError(errorContext)
```

All application code must use this abstraction rather than calling the vendor SDK directly. Add environment controls:

- Production: analytics enabled according to consent and policy.
- Development/test: use a clearly marked developer/test stream or disable collection.
- Never mix local, staging, automated-test, and production data.
- Add event versioning only when the meaning or schema changes.
- Add a request/event ID where deduplication is needed.
- Log events after the business action succeeds, not merely when a button is clicked.
- For important actions, prefer a server-confirmed event or reconciliation process.

## 5. Identity and user segments

Use the analytics user identity only after authenticated consent and only according to the project privacy policy. Do not send email or Google profile data as event parameters.

Set controlled user properties or audience attributes such as:

- `auth_method`: `google`, `email`, or `unknown`.
- `account_state`: `anonymous`, `authenticated`.
- `creator_status`: `never_uploaded`, `uploader`, `active_uploader`.
- `reader_status`: `never_read`, `reader`, `active_reader`.
- `engagement_stage`: `new`, `activated`, `returning`, `dormant`.
- `consent_state`: only if legally and technically appropriate.

Derive `uploader` from a successful server-confirmed upload. Derive `reader` from a meaningful note/PYQ view, not an accidental page impression. Keep authoritative user roles and counts in the application database; analytics is for behavior analysis, not authorization.

## 6. Canonical event taxonomy

Use lowercase snake_case names and a stable parameter schema. Create `docs/analytics/event-taxonomy.md` with each event, trigger, required parameters, optional parameters, source, and validation rule.

### Acquisition and authentication

- `page_view` or the platform's standard page-view event.
- `sign_up`: `method`.
- `login`: `method`.
- `login_failed`: `method`, `reason_code` without sensitive details.
- `logout`.
- `consent_updated`: `analytics_allowed`.

### Activation and navigation

- `dashboard_viewed`.
- `feature_viewed`: `feature_name`.
- `search_submitted`: `search_area`, `result_count`, `query_length` only; never send the raw query if it can contain personal or sensitive text.
- `filter_applied`: `area`, `filter_name`.

### Notes and PYQs

- `content_list_viewed`: `content_type`, `source`, `result_count`.
- `content_viewed`: `content_type`, `content_id` as a non-sensitive internal identifier or coarse content key, `category`.
- `content_engaged`: `content_type`, `engagement_type` such as `read`, `download`, `bookmark`, `share`.
- `content_reported`: `content_type`, `reason_code`.
- `upload_started`: `content_type`.
- `upload_completed`: `content_type`, `file_type`, `file_size_bucket`, `category`, `duration_ms`.
- `upload_failed`: `content_type`, `failure_code`, `stage`.
- `content_published` or `content_moderation_status_changed` when applicable.

### Profile and storeroom

- `profile_viewed`.
- `profile_updated`: changed field categories only, never values.
- `storeroom_viewed`.
- `item_saved`.
- `item_removed`.
- `download_started` and `download_completed` only if downloads exist.

### Reliability and friction

- `client_error`: `error_code`, `surface`, `recoverable`.
- `api_error`: `route_group`, `status_class`, `operation`; never tokens, request bodies, or private content.
- `empty_state_viewed`: `surface`, `reason_code`.
- `feature_blocked`: `feature_name`, `reason_code`.
- `feedback_submitted`: `feedback_type`, `rating_bucket`; do not send free text by default.

Do not create events for every hover, keystroke, timer tick, or generic click. Add an event only when it answers a product or reliability question.

## 7. User classification logic

Implement classifications in a documented, deterministic way:

- Viewer: authenticated or anonymous user with at least one meaningful `content_viewed` event.
- Reader: viewer with meaningful reading engagement, such as minimum active time or progress threshold, defined in code and documented.
- Uploader: user with a successful `upload_completed` event confirmed by the backend.
- Upload-only user: uploader with no qualifying content-reading event during the analysis window.
- Reader-only user: qualifying reader with no successful upload during the analysis window.
- Contributor-reader: both uploader and reader.

Use cohort windows such as first 7 days, 30 days, and rolling 28 days. Do not infer permanent identity from a single browser or device signal.

## 8. Authentic traffic and data quality

Implement:

- Separate production, staging, development, and automated-test measurement destinations.
- Mark developer/test traffic explicitly.
- Exclude internal traffic using the analytics platform's supported internal-traffic configuration after testing; do not rely only on frontend code.
- Keep raw/debug data available temporarily for validation before applying permanent exclusions.
- Prevent duplicate page views and duplicate upload events.
- Ensure SPA route changes produce one logical page view per route transition.
- Preserve campaign parameters and use consistent UTM naming.
- Add server-side rate limits and bot/security controls separately from analytics.
- Treat analytics as non-authoritative for fraud detection; compare analytics with server logs, authentication records, upload records, and database counts.
- Create `docs/analytics/data-quality.md` with event-volume checks, missing-parameter checks, duplicate checks, timestamp checks, and reconciliation queries.

## 9. Feature interest and annoyance

Interest signals:

- unique users viewing a feature;
- repeat use;
- completion rate;
- content views, saves, downloads, or uploads generated;
- return rate and cohort retention;
- time to meaningful action.

Friction signals:

- repeated errors;
- empty states;
- failed uploads;
- repeated back-and-forth navigation;
- abandonment after `*_started` without completion;
- slow API or page timing;
- explicit low ratings or reports;
- rage-click-like patterns only if implemented carefully and privacy-safe.

Never label a feature “annoying” from low usage alone. Combine behavioral data with explicit feedback and error/performance data. Provide a lightweight feedback mechanism with predefined categories and optional separate product feedback storage.

## 10. Dashboards and reports

Create a dashboard specification in `docs/analytics/dashboard-spec.md` with:

- Acquisition: users, signup rate, login method, source/medium/campaign.
- Activation: first meaningful content view, first save, first upload, time to activation.
- Reader funnel: list view → content view → meaningful engagement → save/download/return.
- Contributor funnel: upload started → upload completed → published/approved.
- Segments: reader-only, uploader-only, contributor-reader, anonymous, authenticated.
- Feature adoption and repeat use by feature.
- Error and abandonment rates by feature and device/browser.
- Retention: first-day, seventh-day, and twenty-eighth-day return cohorts.
- Data-quality panel: event volume, missing fields, duplicate rate, rejected events, and server reconciliation.

Use aggregate reports. Avoid exposing individual users unless there is a legitimate operational need and appropriate access control.

## 11. Implementation workflow in Antigravity

Use this exact sequence:

1. Inspect the repository and identify the framework, analytics implementation, environment files, routes, backend, database, and tests.
2. Create a Conductor plan with milestones: audit, taxonomy, abstraction, identity, core instrumentation, server reconciliation, validation, dashboard docs, and rollout.
3. Write the audit and event taxonomy before changing production code.
4. Implement the analytics abstraction and typed event contracts.
5. Instrument authentication, navigation, content, uploads, profile, storeroom, errors, and performance.
6. Add unit tests for event names, required parameters, privacy redaction, deduplication, and success/failure triggers.
7. Add integration tests for Google login, email login, note viewing, PYQ viewing, upload success, upload failure, save/remove, logout, and route transitions.
8. Run a local debug validation and inspect the analytics debug view or equivalent.
9. Deploy to staging with test traffic clearly marked.
10. Reconcile staging analytics with server/database records.
11. Roll out behind a feature flag or gradual release.
12. Monitor for at least one normal usage cycle before applying permanent exclusions or deleting old tracking.
13. Update documentation and provide a migration/rollback plan.

## 12. Acceptance criteria

The redesign is complete only when:

- Every canonical event has an owner, trigger, schema, and test.
- No analytics payload contains email, name, token, password, raw note content, or sensitive free text.
- Google and email authentication are distinguishable through a safe method property.
- Successful uploads are server-confirmed and distinguish uploaders from readers.
- Reader-only, uploader-only, and contributor-reader cohorts can be generated.
- SPA navigation does not create duplicate page views.
- Failed actions and abandonment are measurable.
- Development, staging, internal, and production traffic are separable.
- Analytics totals reconcile with server-side counts within a documented tolerance.
- Debug mode proves each major flow before production release.
- Existing functionality and performance remain intact.

## 13. Required deliverables

Create or update:

- `docs/analytics/audit.md`
- `docs/analytics/event-taxonomy.md`
- `docs/analytics/data-quality.md`
- `docs/analytics/dashboard-spec.md`
- `docs/analytics/privacy.md`
- `docs/analytics/rollout-and-rollback.md`
- typed analytics event definitions;
- analytics abstraction/service;
- automated tests;
- a final implementation report listing changed files, events, known limitations, and next steps.

At the end, show the user:

1. What was found to be wrong.
2. What was changed.
3. How to verify events in debug mode.
4. Which analytics console custom definitions and audiences must be created manually.
5. Which data cannot be backfilled because it was not collected previously.
6. How to roll back safely.
