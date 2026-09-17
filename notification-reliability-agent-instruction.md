# AbhiHub Cross-Device Notification Reliability Instructions

## Objective

Audit and repair AbhiHub notifications so authenticated users can reliably receive relevant notifications on supported laptops and mobile devices, while the application remains secure, privacy-conscious, testable, and production-ready.

Support the actual notification channels found in the repository. Do not assume that browser push, email, in-app, Android, and iOS all exist. First identify the current implementation.

## Non-negotiable rules

- Use Ponytail coding rules and the Conductor workflow.
- Work on a new branch created from the current branch, for example `fix/notifications-cross-device`.
- Do not discard existing user changes.
- Do not commit secrets, private keys, FCM service-account JSON, tokens, or real user data.
- Never log notification tokens, authorization headers, message contents containing private data, or full user details.
- Notifications must be opt-in where required. Do not silently request permission on the first page load.
- Do not send duplicate notifications when a provider retries delivery.
- Do not claim guaranteed delivery: browser, operating-system, battery, permission, network, and vendor policies can affect delivery.
- Do not break the application if the notification provider is unavailable.

## Phase 1: inspect before implementation

Create `docs/notifications/audit.md` after inspecting:

- frontend framework and routing model;
- backend/API framework;
- authentication and user identity model;
- current notification UI and preferences;
- current browser push, FCM, Web Push, email, or in-app implementation;
- service-worker files and registration scope;
- Firebase project configuration and SDK versions, if present;
- VAPID configuration, if present;
- server-side notification sender and retry logic;
- token/device-subscription database schema;
- notification triggers for uploads, notes, PYQs, profile, storeroom, messages, moderation, and system alerts;
- mobile support: responsive web, PWA, Android app, iOS app, or none;
- deployment HTTPS, domains, subdomains, reverse proxy, CDN, and caching;
- existing tests, logs, monitoring, and analytics.

Report the exact current failure if reproducible. Inspect browser console, service-worker console, network requests, server logs, provider responses, and database records without exposing secrets.

## Phase 2: define the delivery model

Document which channels AbhiHub supports:

- in-app notifications;
- web push on desktop/laptop browsers;
- web push on mobile browsers/PWA;
- Android native push;
- iOS native push;
- email fallback.

For every channel document: supported platforms, permission state, subscription/token lifecycle, sender, retry policy, expiry behavior, deep link, preference controls, and test method.

If AbhiHub is a web application using Firebase Cloud Messaging, verify all of the following:

- production is served over HTTPS;
- a messaging service worker exists at the correct web root/scope;
- the service worker is registered and controls the intended pages;
- the web push VAPID public key is configured in the client;
- the private VAPID/service-account credentials exist only on the server or provider configuration;
- permission is requested from a user action after explaining the benefit;
- a token is obtained only after permission is granted;
- the token/subscription is securely registered with the authenticated user on the server;
- foreground and background messages are handled separately;
- notification click actions open safe allowlisted routes;
- stale or invalid tokens are removed after provider errors;
- multiple devices per user are supported.

Firebase's web messaging requires HTTPS and a service worker, and web push uses VAPID credentials. Verify the deployment rather than assuming local behavior represents production.

## Phase 3: data model and subscription lifecycle

Create or verify a device-subscription table/collection with fields similar to:

- `id`;
- `user_id`;
- `channel`: `web_push`, `android_push`, `ios_push`, `email`, `in_app`;
- `provider`;
- `token_or_endpoint_hash`: store the minimum necessary value and protect it;
- encrypted provider token/endpoint where required;
- `platform`: `desktop`, `android`, `ios`, `unknown`;
- `browser` and app version, if useful and privacy-safe;
- `permission_state`;
- `enabled`;
- `last_seen_at`;
- `last_success_at`;
- `last_failure_at`;
- `failure_code`;
- `created_at`, `updated_at`, `revoked_at`.

Rules:

- Never use a token as a user identity.
- A user may have multiple active devices.
- Upserting the same subscription must be idempotent.
- Unsubscribe must revoke only the current device subscription unless the user explicitly chooses all devices.
- On logout, decide and document whether the device subscription remains linked for future notifications; do not accidentally send private notifications to a shared device.
- On account deletion, revoke and delete all associated subscriptions according to the retention policy.
- Treat provider token changes as normal and update the record.
- Remove or disable invalid subscriptions after provider-confirmed permanent failure.
- Protect subscription endpoints with authentication, CSRF protection where applicable, validation, and rate limiting.

## Phase 4: notification contract

Create `docs/notifications/catalog.md` containing a canonical notification catalog. Every notification must define:

- stable notification type;
- trigger and source of truth;
- recipient authorization rule;
- title and body template;
- channel eligibility;
- preference category;
- deduplication key;
- priority and urgency;
- safe allowlisted destination route;
- expiry time;
- localization behavior;
- audit/logging behavior;
- privacy classification.

Use a server-generated notification record or outbox pattern for important events. Do not rely only on a client-side button click.

Example types:

```text
upload_processed
upload_failed
content_approved
content_rejected
new_relevant_content
storeroom_update
account_security
system_announcement
```

Do not notify users for every low-value event. Provide preferences such as:

- security and account;
- upload/moderation;
- saved-content updates;
- new content recommendations;
- system announcements.

## Phase 5: reliable sending

Implement or repair a server-side delivery pipeline:

1. Create an idempotent notification/outbox record.
2. Resolve only authorized recipients and active subscriptions.
3. Apply user preferences and quiet hours.
4. Generate a safe, localized payload.
5. Send through the provider.
6. Record provider outcome without storing sensitive payloads in logs.
7. Retry transient failures with bounded exponential backoff.
8. Do not retry permanent failures.
9. Deduplicate using a stable key and time window.
10. Mark each attempt with status and reason.
11. Remove invalid subscriptions when confirmed by the provider.
12. Keep in-app history independent from push delivery status.

Use a queue or background worker if sending can delay web requests. Notification failure must not cause the originating upload, save, authentication, or content action to fail.

## Phase 6: client behavior

Implement a clear notification settings experience:

- show supported channels and current permission state;
- explain why permission is needed before invoking the browser prompt;
- provide Enable, Disable, and Test notification controls;
- show a useful message for blocked, denied, unsupported, insecure, or unavailable states;
- show last successful subscription sync without exposing tokens;
- allow per-category preferences;
- allow “sign out this device” and “disable all notifications” where appropriate;
- handle token refresh and service-worker updates;
- handle foreground notifications without duplicate display;
- handle background notifications through the service worker;
- validate notification click URLs against an allowlist;
- navigate to the relevant AbhiHub page after a click;
- avoid requesting permission repeatedly after denial.

For mobile web/PWA, test the installed and non-installed experiences separately. A responsive website is not automatically equivalent to a native mobile app.

## Phase 7: service worker and caching checks

Inspect service-worker registration and scope carefully:

- use the correct production path;
- ensure the file is served with the correct content type;
- ensure deployment does not cache an obsolete service worker indefinitely;
- use an explicit version/update strategy;
- keep notification event handling compatible with the deployed SDK;
- prevent multiple competing service workers;
- verify that the service worker can be updated and removed safely;
- verify notification click handling when the app is closed, backgrounded, or already open.

## Phase 8: testing matrix

Create `docs/notifications/test-matrix.md` and test at least:

### Permission and subscription

- permission granted;
- permission denied;
- permission blocked in browser settings;
- unsupported browser;
- non-HTTPS environment;
- token/subscription creation;
- token refresh;
- unsubscribe;
- logout/login on the same device;
- multiple devices for one user;
- two users sharing one laptop/browser profile where relevant.

### Delivery state

- foreground tab;
- background tab;
- closed browser;
- laptop sleep/wake;
- Android mobile browser/PWA;
- iOS supported browser/PWA behavior if applicable;
- slow network;
- offline then reconnect;
- provider transient failure;
- invalid/expired token;
- duplicate provider retry;
- notification click and deep link;
- notification preference disabled;
- quiet hours.

### Security and correctness

- user A cannot receive user B's notification;
- unauthorized users cannot register a subscription for another user;
- private note/content details are not leaked in titles, bodies, URLs, logs, or analytics;
- notification routes cannot redirect to an untrusted domain;
- CSRF, rate limiting, and authorization are tested;
- notification sending does not block or fail the source action;
- one logical event produces no unintended duplicates.

Use local/staging test accounts and test provider credentials. Never use real user data.

## Phase 9: observability and analytics

Add safe metrics and logs:

- subscription attempts, successes, failures, and permission states;
- notification records created;
- send attempts by provider and channel;
- delivery/provider outcomes;
- invalid-token rate;
- retry count;
- click/open events where supported;
- unsubscribe and disable rates;
- latency from source event to send attempt;
- duplicate rate;
- notification errors by platform/browser.

Do not treat a provider “accepted” response as guaranteed display. Clearly distinguish queued, accepted, delivered if available, clicked, failed, and unknown.

Add analytics events only through the existing analytics abstraction, for example:

```text
notification_permission_prompted
notification_permission_changed
notification_subscription_created
notification_subscription_failed
notification_sent
notification_clicked
notification_disabled
```

Do not send notification tokens, email addresses, private message text, note contents, or raw provider error payloads to analytics.

## Phase 10: production checklist

Verify:

- production HTTPS and correct domain;
- correct Firebase/FCM project and environment configuration;
- VAPID/public configuration is correct;
- private credentials are server-only;
- service worker is deployed at the expected root;
- production OAuth origins and redirects are correct;
- database indexes and migrations are applied;
- worker/queue is running;
- retry and dead-letter behavior exists;
- monitoring and alerts are configured;
- notification preferences are documented;
- privacy policy and consent behavior are reviewed;
- rollback can disable sending without breaking the app;
- staging tests pass on laptop and mobile devices.

## Required deliverables

Create or update:

- `docs/notifications/audit.md`;
- `docs/notifications/catalog.md`;
- `docs/notifications/test-matrix.md`;
- `docs/notifications/production-runbook.md`;
- database migration/model for subscriptions if required;
- notification service and provider adapter;
- service-worker registration/handler;
- notification preferences UI;
- automated tests;
- monitoring and analytics documentation.

## Completion report

At the end, report:

1. The original notification failure and root cause.
2. Supported laptop and mobile platforms.
3. Changed files and migrations.
4. Notification channels implemented.
5. Permission and subscription behavior.
6. Test results by device/browser.
7. Provider and environment settings required manually.
8. Known platform limitations.
9. Monitoring and rollback procedure.
10. Any work still required before production.

Stop before pushing, merging, or deploying. Ask for explicit approval before any external Git or deployment action.
