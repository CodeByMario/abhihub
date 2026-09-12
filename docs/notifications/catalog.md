# AbhiHub Notification Catalog

**Version:** 1.0.0  
**Last Updated:** 2026-09-11  
**Source of Truth:** AbhiHub Backend & Database Models (`abhihub.notifications`, `abhihub.push_subscriptions`)  

---

## 1. Overview & Policy

This catalog defines the canonical set of notifications supported by AbhiHub. Every notification event dispatched across in-app or Web Push channels must strictly conform to a defined type contract.

### Core Delivery Principles
1. **Opt-In & Preference Respect**: Notifications are never sent if the user has disabled the corresponding preference category.
2. **Authorization Boundary**: Recipients are resolved strictly based on authenticated relationship to the event (e.g. uploader of the document, recipient of the chat message).
3. **Privacy by Design**: Sensitive message details, tokens, passwords, and private document URLs are never embedded in push notification payloads.
4. **Allowlisted Routing**: Deep links must map strictly to safe, relative routes within `abhihub.com`.

---

## 2. Notification Type Contracts

### 2.1. `upload_processed` (Upload Successful)
- **Type Identifier**: `upload_processed`
- **Trigger & Source of Truth**: Background upload notifier task (`scheduled_tasks.py` / `upload_notifier.py`) or document ingestion pipeline.
- **Recipient Authorization**: Authenticated uploader (`documents.uploader_id = profiles.id`).
- **Title Template**: `"Upload Successful! 🎉"`
- **Body Template**: `"Your resource '{document_title}' has been processed and is now live for students!"`
- **Channel Eligibility**: In-App (`notifications`), Web Push (`push_subscriptions`).
- **Preference Category**: `uploads` (`notif_uploads_enabled`)
- **Deduplication Key**: `upload_success:{document_id}`
- **Priority & Urgency**: Normal (Push Urgency: `normal`)
- **Destination Route**: `/dashboard` or `/resource/{document_id}`
- **Expiry Time (TTL)**: 24 hours (86,400 seconds)
- **Privacy Classification**: Low (Public document title)

---

### 2.2. `file_view` (Document Viewed / Downloaded)
- **Type Identifier**: `file_view`
- **Trigger & Source of Truth**: Document view logging (`methods/supabase_helper.py:log_file_view` / `save_file_access`).
- **Recipient Authorization**: Document uploader (`documents.uploader_id = profiles.id`, excluding self-views).
- **Title Template**: `"Someone viewed your resource"`
- **Body Template**: `"{viewer_name} just viewed your file '{document_title}'"`
- **Channel Eligibility**: In-App (`notifications`) only (avoids noisy push spam).
- **Preference Category**: `uploads` (`notif_uploads_enabled`)
- **Deduplication Key**: `file_view:{document_id}:{viewer_id}:{date_bucket_hourly}`
- **Priority & Urgency**: Low
- **Destination Route**: `/dashboard`
- **Expiry Time (TTL)**: 7 days
- **Privacy Classification**: Low (Viewer public nickname)

---

### 2.3. `chat_message` (New Direct Message)
- **Type Identifier**: `chat_message`
- **Trigger & Source of Truth**: Chat messaging controller (`app.py:send_chat_message` / `chat_messages` table).
- **Recipient Authorization**: Recipient user (`chat_messages.recipient_id = profiles.id`).
- **Title Template**: `"New message from {sender_name}"`
- **Body Template**: `"You have a new message: {message_preview_truncated}"`
- **Channel Eligibility**: In-App (`notifications`), Web Push (`push_subscriptions`).
- **Preference Category**: `chat` (`notif_chat_enabled`)
- **Deduplication Key**: `chat:{message_id}`
- **Priority & Urgency**: High (Push Urgency: `high`)
- **Destination Route**: `/chat?user={sender_id}`
- **Expiry Time (TTL)**: 48 hours
- **Privacy Classification**: Moderate (Message preview truncated to 40 characters; no secrets).

---

### 2.4. `quota_deduction` (Study Credit Used / Refilled)
- **Type Identifier**: `quota_deduction`
- **Trigger & Source of Truth**: Document view authorization proxy (`app.py:view_doc` credit debit).
- **Recipient Authorization**: Active session user (`profiles.id`).
- **Title Template**: `"Study Credits Updated"`
- **Body Template**: `"1 credit used to view '{document_title}'. You have {credits_remaining} credits left today."`
- **Channel Eligibility**: In-App (`notifications`).
- **Preference Category**: `account` (`notif_push_enabled`)
- **Deduplication Key**: `quota_debit:{user_id}:{document_id}:{timestamp_minute}`
- **Priority & Urgency**: Normal
- **Destination Route**: `/settings#section-study-credits`
- **Expiry Time (TTL)**: 24 hours
- **Privacy Classification**: Private (Personal credit balance).

---

### 2.5. `crush_match` (Crush Match Alert)
- **Type Identifier**: `crush_match`
- **Trigger & Source of Truth**: Mutual crush match calculation (`user_crushes` table).
- **Recipient Authorization**: Matched user (`user_crushes.target_id = profiles.id`).
- **Title Template**: `"It's a Match! 💖"`
- **Body Template**: `"Someone you like has a mutual crush on you! Check your profile."`
- **Channel Eligibility**: In-App (`notifications`), Web Push (`push_subscriptions`).
- **Preference Category**: `crush` (`notif_crush_enabled`)
- **Deduplication Key**: `crush_match:{user_a}:{user_b}`
- **Priority & Urgency**: High
- **Destination Route**: `/profile`
- **Expiry Time (TTL)**: 7 days
- **Privacy Classification**: High (Private mutual connection; no identities disclosed in push payload).

---

### 2.6. `admin_broadcast` (System Announcement)
- **Type Identifier**: `admin_broadcast`
- **Trigger & Source of Truth**: Admin notification panel (`/api/admin/send-notification`).
- **Recipient Authorization**: Verified Admin origin (`admin_email == session.user.email`), dispatched to all opted-in subscribers.
- **Title Template**: `"{custom_admin_title}"`
- **Body Template**: `"{custom_admin_message}"`
- **Channel Eligibility**: In-App (`notifications`), Web Push (`push_subscriptions`).
- **Preference Category**: `announcements` (`notif_push_enabled`)
- **Deduplication Key**: `broadcast:{broadcast_id}`
- **Priority & Urgency**: High
- **Destination Route**: Allowlisted route (defaults to `/dashboard`).
- **Expiry Time (TTL)**: 72 hours
- **Privacy Classification**: Public announcement.

---

## 3. Preference Categories & Channel Matrix

| Category | Key | In-App | Web Push | Default State | User Configurable |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Uploads & Resources** | `notif_uploads_enabled` | Yes | Yes | Enabled | Yes (`/settings`) |
| **Direct Chat** | `notif_chat_enabled` | Yes | Yes | Enabled | Yes (`/settings`) |
| **Crush Matches** | `notif_crush_enabled` | Yes | Yes | Enabled | Yes (`/settings`) |
| **Account & Credits** | `notif_account_enabled` | Yes | No | Enabled | Yes (`/settings`) |
| **System Announcements** | `notif_push_enabled` | Yes | Yes | Enabled | Yes (`/settings`) |

---

## 4. Destination Route Allowlist

All notification click actions must validate against the following relative path prefixes:
- `/dashboard`
- `/profile`
- `/resource/*`
- `/chat*`
- `/settings*`
- `/notifications`
- `/pyqs`
- `/notes`

Any URL with an external domain or non-allowlisted path must fallback to `/dashboard`.
