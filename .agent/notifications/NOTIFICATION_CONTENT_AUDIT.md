# AbhiHub Notification Content Audit (Phase 2)

**Project:** AbhiHub  
**Module:** Notification System  
**Initiative:** Notification Quality & Reliability 2.0  
**Phase:** Phase 2 Content Audit  
**Status:** Audit Complete — Pending Implementation Approval  
**Date:** 2026-11-10  

---

## 1. Executive Summary

A comprehensive content audit of all notification generation points across the AbhiHub codebase was conducted in accordance with Phase 2 guidelines.

The audit identified critical content defects that violate professional brand standards, induce artificial urgency, and trigger browser spam penalties (e.g., Google Chrome Abusive Notification Enforcement). Most notably, a centralized utility function (`psychologize_notification`) systematically alters truthful system events into clickbait hooks with emojis and speculative claims.

---

## 2. Audit Matrix against Phase 2 Criteria

| Criteria | Status | Code Evidence | Impact & Findings |
|---|---|---|---|
| **1. Misleading Titles** | **FAIL** | `push_notifications.py:164,179,193` | Titles are overwritten with speculative claims: *"Your notes are live! 👀 First views rolling in..."*, *"Resource unlocked! ⚡ Quick tip inside..."*, *"Did you catch this yet? 👀"* |
| **2. Excessive Promotional Language** | **FAIL** | `push_notifications.py:166,174` | Artificial hype phrases injected into educational notifications: *"unlocked a verified boost! 🎖️"*, *"Tap to check your new leaderboard rank and rewards"* |
| **3. Unnecessary Capital Letters** | **WARN** | `methods/upload_notifier.py:72`, `push_api.py:160` | ALL-CAPS acronyms and shouty phrasing in auto-generated text (e.g. *"OFF"*, *"UP"*, *"DOWN"*, *"FIRST VIEWS"*) |
| **4. Excessive Emojis** | **FAIL** | `push_notifications.py:140-196`, `payment_engine.py:689`, `supabase_helper.py:2841` | Pervasive emojis in notifications: `👀`, `⚡`, `🎖️`, `💬`, `🔥`, `💸`, `📄`, triggering spam filters |
| **5. Repeated / Broadcast Flooding** | **FAIL** | `supabase_helper.py:2894`, `upload_notifier.py:72` | Every new upload broadcasts a push notification to **all registered users** across the platform; uploader receives a duplicate push 55 mins later |
| **6. Unclear Sender Identity** | **WARN** | `app.py:2054`, `sw.js:1142` | Default notifications omit sender brand context or use vague senders like *"A classmate"* instead of *"AbhiHub · Chat"* |
| **7. Misleading Destination URLs** | **FAIL** | `upload_notifier.py:92`, `routes/admin.py:652` | Upload notifications navigate to `/dashboard` instead of the specific resource `/resource/<id>`; Admin notifications default fallback to `/premium` |
| **8. Excessive Notification Frequency** | **WARN** | `push_notifications.py:91-93` | Platform broadcasts bypass per-user category opt-outs; daily cap (6/day) is in-memory only and lost on server restart |
| **9. Unsanitized User-Generated Content** | **FAIL** | `app.py:2053`, `supabase_helper.py:2842` | Raw user titles and message previews are concatenated into notification payloads without character sanitization or length bounds |

---

## 3. Detailed Audit by Generation Point

### 3.1 Upload Success Notifier
- **Location:** [`methods/upload_notifier.py:89-94`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/upload_notifier.py#L89-L94)
- **Trigger:** Background worker runs 55 minutes post-upload.
- **Current Copy:**
  - *Title:* `Your notes are live! 👀 First views rolling in...`
  - *Body:* `Students in your branch are preparing right now. Tap to see who views '{file_name}' first!`
  - *Destination:* `/dashboard` (Misleading: does not link to the file)
- **Defects:** Fake urgency, unverified claim ("Students in your branch are preparing right now"), decorative emoji (`👀`), incorrect destination URL.
- **Recommended Official Copy:**
  - *Title:* `AbhiHub · Document Published`
  - *Body:* `"{file_title}" is now published and available to students.`
  - *Destination:* `/resource/{doc_id}`

---

### 3.2 Platform-Wide Upload Broadcast
- **Location:** [`methods/supabase_helper.py:2841, 2894`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/supabase_helper.py#L2841-L2894)
- **Trigger:** Fired immediately on document upload via `notify_new_upload()`.
- **Current Copy:**
  - *Title:* `📄 New File Uploaded!`
  - *Body:* `"{clean_title}" was just uploaded for {subject}. Tap to open and view.`
  - *Action:* `send_notification_to_all(...)` (Broadcasts to EVERY user in the database!)
- **Defects:** Emoji in title (`📄`), severe spam risk (10 uploads = 10 push notifications to all users in one day), lack of branch/college targeting.
- **Recommended Policy:**
  - Stop broadcasting push notifications to all users on every single upload.
  - Limit to targeted in-app feed or daily digest for students enrolled in the same subject/college.

---

### 3.3 Credit / Quota Deduction Notifier
- **Location:** [`app.py:981-995`](file:///e:/Users/abhihub/New%20folder/abhihub/app.py#L981-L995) & [`push_notifications.py:178`](file:///e:/Users/abhihub/New%20folder/abhihub/push_notifications.py#L178)
- **Trigger:** User accesses a monetized document.
- **Generated Copy:** `Unlocked: {doc_title} ({credits} Cr)`
- **Mutated Copy (via `psychologize_notification`):**
  - *Title:* `Resource unlocked! ⚡ Quick tip inside...`
  - *Body:* `{body} Tap to view key formulas and study highlights.`
- **Defects:** Clickbait promise ("Quick tip inside", "key formulas and study highlights") that is not actually present in the file. Emoji (`⚡`).
- **Recommended Official Copy:**
  - *Title:* `AbhiHub · Credit Deduction`
  - *Body:* `{credits} credit(s) used to access "{doc_title}". Remaining balance: {balance} credits.`
  - *Destination:* `/resource/{record_id}`

---

### 3.4 Peer Chat Notifications
- **Location:** [`app.py:2054`](file:///e:/Users/abhihub/New%20folder/abhihub/app.py#L2054) & [`push_notifications.py:183`](file:///e:/Users/abhihub/New%20folder/abhihub/push_notifications.py#L183)
- **Trigger:** Peer sends a direct message.
- **Generated Copy:** `New message from {sender}`
- **Mutated Copy (via `psychologize_notification`):**
  - *Title:* `{sender} left you a study note... 💬`
  - *Body:* `You have an unread update from {sender}. Tap to see what was shared!`
- **Defects:** Obscures the actual message preview, creates artificial curiosity, uses emoji (`💬`).
- **Recommended Official Copy:**
  - *Title:* `AbhiHub · Message from {sender}`
  - *Body:* `{sanitized_preview_up_to_100_chars}`
  - *Destination:* `/chat?peer={sender_id}`

---

### 3.5 Payout & Wallet Notifications
- **Location:** [`methods/payment_engine.py:689`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/payment_engine.py#L689)
- **Trigger:** Creator payout request submitted.
- **Current Copy:**
  - *Title:* `Payout Requested 💸`
  - *Body:* `₹{amount:.2f} payout request submitted. Expected within 3 business days.`
- **Defects:** Unprofessional currency emoji (`💸`) in transactional financial notification.
- **Recommended Official Copy:**
  - *Title:* `AbhiHub · Payout Submitted`
  - *Body:* `Your payout request for ₹{amount:.2f} has been received. Expected processing: 3 business days.`
  - *Destination:* `/earnings`

---

### 3.6 Admin Broadcast Tool
- **Location:** [`routes/admin.py:652`](file:///e:/Users/abhihub/New%20folder/abhihub/routes/admin.py#L652) & [`push_notifications.py:191`](file:///e:/Users/abhihub/New%20folder/abhihub/push_notifications.py#L191)
- **Trigger:** Admin sends announcement.
- **Mutated Copy (via `psychologize_notification`):**
  - Injects `Did you catch this yet? 👀 {title}`
  - Defaults destination to `/premium`
- **Defects:** Unprofessional prefix, emoji, promotional redirect.
- **Recommended Official Copy:**
  - *Title:* `AbhiHub · Announcement: {admin_title}`
  - *Body:* `{admin_body}`
  - *Destination:* Validated internal URL (defaults to `/dashboard` or `/notifications`, never `/premium`).

---

## 4. Brand Identity & Copy Standards (WCAG & Anti-Spam Compliance)

### 4.1 Required Brand Hierarchy
Every notification must follow this structure:
```text
Title:       AbhiHub · [Category / Event Type]
Body:        [One factual, educational, concise sentence with clear context]
Destination: [Direct deep-link matching the content]
Icon:        /static/images/android-chrome-192x192.png
Badge:       /static/images/favicon-32x32.png
```

### 4.2 Prohibited Patterns
1. **NO Decorative Emojis:** Remove all emojis (`👀`, `⚡`, `🎖️`, `💬`, `🔥`, `💸`, `📄`).
2. **NO Curiosity Gaps:** Never use phrases like *"Did you catch this yet?"*, *"Quick tip inside..."*, *"Tap to see who views first!"*.
3. **NO Fake Urgency:** Never imply time sensitivity unless an actual university examination date or deadline exists.
4. **NO Global Broadcasts for Individual Uploads:** Single uploads must never trigger platform-wide push broadcasts.

---

## 5. Next Steps (Pending Approval for Implementation)

Upon user approval:
1. Decommission or refactor `psychologize_notification()` in [`push_notifications.py`](file:///e:/Users/abhihub/New%20folder/abhihub/push_notifications.py) to return clean, standardized notifications.
2. Update [`methods/upload_notifier.py`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/upload_notifier.py) with official copy and direct `/resource/{id}` deep-linking.
3. Remove global push broadcast from [`methods/supabase_helper.py`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/supabase_helper.py#L2894) for single document uploads.
4. Clean financial notification titles in [`methods/payment_engine.py`](file:///e:/Users/abhihub/New%20folder/abhihub/methods/payment_engine.py).
5. Proceed to Phase 3 (Notification Categories & Preference Engine).
