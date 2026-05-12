# Subscription Notifications

## Overview
The subscription notification system sends push notifications to users about new documents, rank updates, and promotional offers. It uses the Web Push protocol with VAPID authentication. Subscriptions are stored in Supabase (`push_subscriptions` table) keyed by user UUID.

## Architecture Flow
1. **Frontend** (`push-notifications.js`) → requests notification permission and subscribes via Push API
2. **Service Worker** (`static/sw.js`, served at `/sw.js`) → handles `push` events, shows native notifications
3. **Backend Subscribe** (`push_api.py` → `push_notifications.py` → `supabase_helper.py`) → saves subscription keyed by user UUID
4. **Backend Send** (`push_notifications.py`) → loads all subscriptions, sends via `pywebpush`
5. **Admin Panel** (`/admin/controle`) → sends broadcast or targeted notifications via `/api/admin/send-notification`

## Relevant Code
- `push_notifications.py` – core functions: `send_notification()`, `send_notification_to_all()`, `send_notification_to_users()`, `add_subscription()`, `load_subscriptions()`
- `push_api.py` – Flask Blueprint with routes: `/api/push/vapid-public-key`, `/api/push/subscribe`, `/api/push/unsubscribe`, `/api/push/status`, `/api/push/send`
- `app.py` – admin routes: `/api/admin/subscribers`, `/api/admin/send-notification`, `/api/admin/notification-history`
- `app.py` – `/sw.js` route serves the service worker from root scope (required for push)
- `static/js/push-notifications.js` – client-side `PushNotifications` object (subscribe/unsubscribe/toggle)
- `static/sw.js` – handles `push`, `notificationclick`, `notificationclose` events
- `methods/supabase_helper.py` – `save_push_subscription()`, `get_all_push_subscriptions()`, `remove_push_subscription_by_endpoint()`, `log_notification()`
- `data/notifications.py` – `Notification` and `PushSubscription` ORM classes
- `generate_vapid.py` – script to generate VAPID key pair
- `methods/upload_notifier.py` – sends upload-success notifications 1 hour after upload
- `scheduled_tasks.py` – APScheduler runs `process_upload_notifications()` every 10 minutes
- `templates/admin_notification_panel.html` – admin UI for sending and viewing notification history

## Scripts
- **Generate VAPID Keys**: `python generate_vapid.py` creates key pair for Web Push authentication
- **Send Test Notification**: `python push_notifications.py --test --user-id <UUID>`
- **Manual Upload Notifications**: `python -c "from scheduled_tasks import run_upload_notifications_task; run_upload_notifications_task()"`

## Environment Variables
- `VAPID_PUBLIC_KEY` – Base64-encoded public key
- `VAPID_PRIVATE_KEY` – Base64-encoded private key
- `VAPID_CLAIMS_EMAIL` – Contact email for VAPID (default: `mailto:admin@abhihub.com`)

## Key Design Details
- Subscriptions are keyed by **user UUID** (from `profiles.id`), not email
- The subscribe endpoint resolves email → UUID via `profiles` table lookup
- Expired/invalid subscriptions (HTTP 404/410 from push service) are auto-removed
- The service worker must be served from `/sw.js` (root scope) — handled by a dedicated Flask route in `app.py`
- Notification history is stored in the `notifications` table; broadcast notifications to 'all' are not logged per-user

## Known Bugs Fixed (May 2026)
1. **Missing `/sw.js` route** — service worker was at `static/sw.js` but registered as `/sw.js`. Flask had no route, so the SW never loaded and push subscriptions silently failed. Fixed by adding a root `/sw.js` route in `app.py`.
2. **Duplicate `send_notification_to_users`** — defined twice in `push_notifications.py`. Removed the less-complete first copy.

## Usage (Frontend)
```js
// Subscribe
const result = await PushNotifications.subscribe();

// Unsubscribe
await PushNotifications.unsubscribe();

// Toggle
await PushNotifications.toggle();

// Check status
const status = await PushNotifications.init();
```

The profile nudge popup (in `p_struct.html`) also offers notification opt-in via `nudgeEnableNotifications()`.
