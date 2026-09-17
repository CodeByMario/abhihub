# AbhiHub Notification Production-Readiness Instructions

## Objective

Diagnose and fix AbhiHub notifications so they work reliably on supported laptop and mobile browsers, in foreground, background, and after the app tab is closed where the platform permits it. Preserve existing behavior, avoid duplicate notifications, respect permission and consent, and document browser/platform limitations.

Do not assume that “notification sent” means “notification displayed.” Verify the complete chain: event creation, backend dispatch, provider response, device/browser subscription, service worker receipt, display, click handling, and analytics.

## Safety and workflow

- Use Ponytail rules and the Conductor workflow.
- Inspect before changing code.
- Create a new branch from the current branch, such as `fix/notifications-cross-platform`.
- Do not discard uncommitted user changes.
- Do not push, merge, deploy, revoke credentials, or change production provider settings without explicit approval.
- Never place FCM private keys, service-account JSON, VAPID private keys, access tokens, or user secrets in client code or Git.
- Do not send notification payloads containing passwords, tokens, private note content, or unnecessary personal information.
- Do not request notification permission automatically on first page load.
- Do not make analytics or notification failures break the core AbhiHub application.

## Phase 1: inspect the current system

Create `docs/notifications/notification-audit.md` containing:

- frontend framework and build system;
- backend framework and notification routes/jobs;
- current provider: FCM, Web Push, OneSignal, or another service;
- web service-worker files and registration scope;
- whether notifications are browser web push, in-app notifications, email, native Android/iOS, or a combination;
- environment-specific provider configuration;
- database tables/collections for device tokens, subscriptions, notification records, delivery status, and preferences;
- all notification triggers in AbhiHub: upload, approval, comments, saved content, account events, system announcements, and errors;
- current permission-request flow;
- foreground and background message handlers;
- notification click and deep-link behavior;
- duplicate-send and retry behavior;
- current browser/device failures and reproducible steps;
- privacy, security, and observability risks.

Before implementation, show the audit and a Conductor plan.

## Phase 2: required architecture

Implement a provider-independent notification service with interfaces similar to:

```text
requestPermission()
registerDeviceOrSubscription()
removeDeviceOrSubscription()
sendNotification()
getNotificationPreferences()
updateNotificationPreferences()
recordDeliveryAttempt()
recordNotificationOpened()
```

Keep provider-specific code behind an adapter. The app should be able to replace or extend FCM/Web Push without rewriting product features.

### Device and subscription records

Store one record per user/device/browser subscription with:

- internal record ID;
- internal user ID;
- platform: `web_desktop`, `web_android`, `web_ios`, or native platform if applicable;
- browser/device metadata at coarse level only;
- provider and token/subscription endpoint, encrypted or protected at rest;
- token/subscription hash for deduplication;
- permission state: `unknown`, `granted`, `denied`, `revoked`;
- app version and service-worker version;
- created, last-seen, last-success, and last-failure timestamps;
- active/revoked state;
- failure code without sensitive payloads.

Never expose tokens to the client UI, analytics reports, logs, or URLs. Remove invalid tokens/subscriptions after provider-confirmed permanent failure. Support multiple active devices per user.

### Notification records

Create or verify a notification record with:

- internal notification ID;
- recipient user ID;
- category and event type;
- safe title/body or a template key plus non-sensitive parameters;
- destination route or internal resource reference;
- idempotency key;
- created and expiry timestamps;
- preference category;
- status such as queued, sent, displayed-unknown, opened, failed;
- provider message ID where available.

Use an idempotency key so retries cannot create duplicate logical notifications. A notification should be marked “opened” only after a click/deep-link event; do not claim that it was displayed unless the platform provides evidence.

## Phase 3: web push requirements

For web push:

- Require HTTPS in production and localhost only for approved local development.
- Register a service worker at the correct origin and scope.
- Ensure the service worker is deployed at the correct path and is not blocked by caching or incorrect headers.
- Use the provider’s supported VAPID/web-push configuration.
- For FCM, configure the public web push key in the client and keep server credentials private.
- Ensure the messaging service worker is available at the expected root/path and is compatible with the application’s bundler.
- Do not register competing service workers that overwrite each other. Merge notification handling with the existing PWA/service worker if one exists.
- Wait for `serviceWorker.ready` before subscribing.
- Handle subscription refresh and token rotation.
- Re-register on login and remove/deactivate the subscription on logout according to the privacy model.
- Request permission from a user-initiated action after explaining the value.
- Handle `default`, `granted`, and `denied` permission states.
- Detect unsupported browsers and show a useful fallback rather than an error.
- Use persistent service-worker notifications for background/mobile delivery.
- Handle notification click, close, and action events.
- Focus an existing AbhiHub tab when possible; otherwise open the correct HTTPS deep link.
- Validate that deep links require authentication and cannot be used for unauthorized access.

Browser push requires secure contexts and an active service worker; persistent notifications are displayed from the service worker. [web:59][web:60][web:67]

## Mobile and laptop support matrix

Create `docs/notifications/support-matrix.md` and test at least:

- Chrome on Windows or Linux;
- Edge on Windows;
- Firefox on desktop if supported;
- Chrome on Android;
- Firefox on Android if supported;
- Safari on macOS if supported;
- Safari on iPhone/iPad for the installed web app/PWA path if supported by the project;
- the exact production domain over HTTPS;
- foreground tab, background tab, closed tab, denied permission, revoked permission, offline/online recovery, and multiple logged-in devices.

Record for every test: browser version, OS, permission state, service-worker state, provider response, displayed result, click result, and known limitation.

Do not promise identical behavior on every mobile browser. When the platform requires installation as a PWA or has restrictions, show that requirement in the UI and documentation.

## Phase 4: delivery reliability

Implement:

- durable queue or job processing for server-triggered notifications;
- bounded retries with exponential backoff;
- idempotency for notification creation and sending;
- provider response logging with redacted fields;
- dead-letter or failed-delivery handling;
- invalid-token cleanup;
- per-user and per-category rate limits;
- quiet hours or notification preferences if appropriate;
- opt-out and category controls;
- safe fallback in-app notification center for users who deny push;
- deduplication across multiple devices where the product requires it;
- ordering or collapse behavior for repeated events;
- expiration for stale notifications.

Do not retry permanent failures such as invalid subscriptions. Do retry temporary provider, network, and rate-limit failures within safe bounds.

## Phase 5: notification UX

Add a clear notification settings screen showing:

- browser/system permission state;
- push enabled/disabled state;
- category preferences;
- registered device/browser entries without revealing tokens;
- a test-notification action available only to the authenticated user;
- instructions for re-enabling notifications after browser denial;
- in-app notification history and unread state if supported.

Use concise notification titles and bodies. Do not put sensitive note text or private data in a notification preview by default. The click destination must be safe, authenticated, and correct.

## Phase 6: observability and analytics

Add structured metrics for:

- permission prompt shown, granted, denied, or dismissed;
- subscription created, refreshed, revoked, and invalidated;
- notification queued, sent, temporary failure, permanent failure;
- service-worker received/display attempt;
- notification clicked/opened;
- deep-link success/failure;
- duplicate prevention;
- delivery latency and provider response category.

Use safe event names such as:

```text
notification_permission_result
push_subscription_registered
notification_queued
notification_send_succeeded
notification_send_failed
notification_opened
notification_settings_updated
```

Do not send notification body text, token values, emails, auth IDs, or private content to analytics. Use a notification category and internal notification ID only where necessary and permitted.

## Phase 7: testing

Add automated tests for:

- permission states;
- unsupported browser behavior;
- service-worker registration failure;
- token/subscription creation and refresh;
- duplicate subscription prevention;
- multiple devices per user;
- login/logout behavior;
- notification preferences;
- authorization of notification destinations;
- idempotent send and retry;
- invalid-token cleanup;
- foreground receipt;
- background receipt;
- notification click and deep link;
- denied permission and in-app fallback;
- offline recovery;
- provider failure without breaking the app.

Add an end-to-end test mode that uses test users, test provider credentials, and a clearly separated staging project. Never test with production user tokens.

## Phase 8: manual verification

Create `docs/notifications/test-runbook.md` with these steps:

1. Log in using a staging test account.
2. Grant notification permission through a user action.
3. Confirm the subscription is stored without exposing its secret value.
4. Send a test notification from the authenticated settings page.
5. Test with the tab focused.
6. Test with the tab in the background.
7. Test with the tab closed.
8. Click the notification and verify the correct authenticated destination.
9. Repeat on Android and laptop browsers.
10. Deny permission and verify the in-app fallback.
11. Revoke/reset browser permission and test recovery.
12. Simulate invalid provider credentials, expired token, timeout, and rate limit.
13. Confirm no duplicate notification is created after retries.
14. Confirm analytics and logs contain no secrets or private content.

## Completion criteria

The feature is ready for review only when:

- The audit and support matrix are complete.
- Desktop and supported mobile scenarios have recorded results.
- Foreground and background handling are implemented.
- Service-worker scope and production HTTPS are verified.
- Multiple devices work for one account.
- Invalid subscriptions are cleaned up.
- Retries are bounded and idempotent.
- Notification clicks open safe, correct routes.
- Denied permission has a usable in-app fallback.
- Preferences and opt-out work.
- Tests pass and production build succeeds.
- No secrets or private content are logged or sent to analytics.
- Rollback and provider-failure procedures are documented.

Stop before pushing, merging, or deploying. Show:

- branch name;
- changed files;
- test results;
- browser/device results;
- unresolved limitations;
- environment variables required by name only;
- exact deployment and rollback steps;
- proposed Git actions.

Ask for explicit approval before pushing or creating a pull request.
