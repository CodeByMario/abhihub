# API Documentation — AbhiHub

## Base URL
- Development: `http://localhost:5000`
- Production: (your deployed domain)

## Auth Pattern
- Session-based (Flask session cookie)
- `@auth_required` decorator on protected routes
- API routes return `401` JSON if unauthenticated:
```json
{ "success": false, "message": "Authentication required" }
```

---

## Standard Response Format
```json
{ "success": true, "data": { ... } }
{ "success": false, "message": "Error description" }
```

---

## 1. Authentication APIs

### POST `/auth`
Exchange Supabase JWT for a Flask session cookie.

- **Auth:** None (this IS authentication)
- **Request:** Bearer token in `Authorization` header
- **Response 200:** `{ "success": true, "user": { "uid", "email", "name" } }`

### GET `/auth-callback`
OAuth callback handler for third-party providers.

- **Auth:** None
- **Response:** Redirects to dashboard or renders error page

### GET `/api/check-auth`
Check if the current session is authenticated.

- **Auth:** None
- **Response 200:** `{ "success": true, "authenticated": true, "user": { ... } }`

### GET `/api/profile-status`
Check if user profile exists and is complete.

- **Auth:** None
- **Response:** `{ "success": true, "has_profile": true }`

---

## 2. Profile APIs

### GET `/api/profile`
Get the authenticated user's profile.

- **Auth:** Required
- **Response:** Full profile object with subscription, quota, and reputation data

### POST `/api/profile/update`
Update user profile information.

- **Auth:** Required
- **Request:** Form data (name, college_id, department_id, etc.)
- **Response:** `{ "success": true, "message": "Profile updated" }`

### GET `/api/check-profile`
Check profile completeness for onboarding flow.

- **Auth:** Required
- **Response:** `{ "success": true, "complete": false, "missing": [...] }`

### GET `/api/users/search`
Search for users by email or name.

- **Auth:** Required
- **Query params:** `q=<search_term>`
- **Response:** `{ "success": true, "users": [...] }`

---

## 3. Document APIs

### POST `/upload`
Upload a new document.

- **Auth:** Required
- **Content-Type:** `multipart/form-data`
- **Fields:** `file`, `title`, `subject_id`, `category`, `year`, `college_id`, `department_id`
- **Response:** `{ "success": true, "document_id": "uuid" }`

### GET `/upload-gate`
Render the upload form with CSRF token.

- **Auth:** Required

### GET `/view_pdf`
View a PDF document.

- **Auth:** Optional (quota checked for free users)
- **Query params:** `doc_id`, `filename`

### GET `/api/view-doc/<doc_id>`
Get document metadata and access info.

- **Auth:** Optional
- **Response:** `{ "success": true, "document": { ... }, "can_access": bool }`

### GET `/api/view-doc/<doc_id>/<filename>`
Serve a specific file from a document.

- **Auth:** Required
- **Response:** File stream

### GET `/api/proxy-file`
Proxy file access through server (bypasses direct Cloudinary URLs).

- **Auth:** Required
- **Query params:** `url`, `doc_id`

### GET `/api/files/all`
List all documents (paginated).

- **Auth:** None
- **Query params:** `page`, `limit`, `subject`, `college`, `branch`, `year`

### GET `/api/recent-documents`
Get recently uploaded documents.

- **Auth:** None
- **Response:** `{ "success": true, "documents": [...] }`

### POST `/api/check-duplicate`
Check if a document already exists before upload.

- **Auth:** Required
- **Request:** `{ "title": "...", "subject_id": "..." }`
- **Response:** `{ "success": true, "duplicate": true/false }`

### POST `/api/document-view`
Record a document view event (for analytics).

- **Auth:** Required
- **Request:** `{ "document_id": "uuid" }`

### GET `/api/file-access-history`
Get user's file access history.

- **Auth:** Required
- **Response:** `{ "success": true, "history": [...] }`

### POST `/api/track-file-access`
Track file access for analytics and quota.

- **Auth:** Required
- **Request:** `{ "file_id": "uuid", "document_id": "uuid" }`

---

## 4. Interaction APIs

### POST `/api/like`
Like a document.

- **Auth:** Required
- **Request:** `{ "document_id": "uuid" }`
- **Response:** `{ "success": true, "like_count": int }`

### POST `/api/bookmark`
Bookmark a document.

- **Auth:** Required
- **Request:** `{ "document_id": "uuid" }`
- **Response:** `{ "success": true, "bookmarked": bool }`

### POST `/api/interactions/like`
Like a document (alternate endpoint).

- **Auth:** Required
- **Request:** `{ "document_id": "uuid" }`
- **Response:** `{ "success": true, "like_count": int }`

### POST `/api/interactions/bookmark`
Bookmark a document (alternate endpoint).

- **Auth:** Required
- **Request:** `{ "document_id": "uuid" }`
- **Response:** `{ "success": true, "bookmarked": bool }`

### GET,POST `/api/interactions/comments/<document_id>`
Get or post comments on a document.

- **Auth:** POST requires auth; GET does not
- **Request (POST):** `{ "comment": "text" }`
- **Response:** `{ "success": true, "comments": [...] }`

### GET,POST `/api/interactions/comments/<doc_id>`
Alternate comments endpoint (different param name).

- **Auth:** POST requires auth; GET does not

---

## 5. Metadata APIs

### GET `/api/colleges`
Get list of all colleges.

- **Auth:** None
- **Response:** `{ "success": true, "colleges": [...] }`

### GET `/api/branches`
Get list of all branches.

- **Auth:** None
- **Response:** `{ "success": true, "branches": [...] }`

### GET `/api/departments`
Get list of all departments.

- **Auth:** None
- **Response:** `{ "success": true, "departments": [...] }`

### GET `/api/semesters`
Get list of all semesters.

- **Auth:** None
- **Response:** `{ "success": true, "semesters": [...] }`

### GET `/api/subjects`
Get list of all subjects.

- **Auth:** None
- **Query params:** `department_id`, `year`, `semester`
- **Response:** `{ "success": true, "subjects": [...] }`

### POST `/api/subjects`
Add a new subject (admin only).

- **Auth:** Admin required
- **Request:** `{ "name": "...", "code": "...", "department_id": "...", "year": ..., "semester": ... }`

### POST `/api/colleges`
Add a new college (admin only).

- **Auth:** Admin required

### POST `/api/departments`
Add a new department (admin only).

- **Auth:** Admin required

### POST `/api/subject-request`
Request a new subject.

- **Auth:** Required
- **Request:** `{ "name": "...", "department_id": "..." }`

---

## 6. Onboarding APIs

### GET `/api/onboarding/status`
Get onboarding status for current user.

- **Auth:** Required
- **Response:** `{ "success": true, "complete": bool }`

### POST `/api/onboarding/welcome-seen`
Mark welcome screen as seen.

- **Auth:** Required
- **Response:** `{ "success": true }`

---

## 7. Admin APIs

### POST `/api/admin/send-notification`
Send push notification to users.

- **Auth:** Admin required
- **Request:** `{ "title": "...", "body": "...", "target": "all|user_id" }`

### POST `/api/admin/approve-document`
Approve a pending document.

- **Auth:** Admin required
- **Request:** `{ "document_id": "uuid" }`

### POST `/api/admin/reject-document`
Reject a pending document.

- **Auth:** Admin required
- **Request:** `{ "document_id": "uuid", "reason": "..." }`

### GET `/api/admin/pending-documents`
Get list of pending document approvals.

- **Auth:** Admin required

### GET `/api/admin/users`
List all users (admin).

- **Auth:** Admin required

### GET `/api/admin/stats`
Get admin dashboard statistics.

- **Auth:** Admin required
- **Response:** `{ "total_users": int, "total_docs": int, "today_uploads": int }`

### GET `/api/admin/subscribers`
List push notification subscribers.

- **Auth:** Admin required

### GET `/api/admin/notification-history`
Get notification history.

- **Auth:** Admin required

### GET `/api/admin/users/<user_id>/stats`
Get stats for a specific user.

- **Auth:** Admin required

### POST `/api/admin/entity/add`
Add a new entity (college, department, subject).

- **Auth:** Admin required
- **Request:** `{ "type": "college|department|subject", "data": {...} }`

### POST `/api/report-suspect`
Report a suspect document or user.

- **Auth:** Required

---

## 8. AI / Metadata Prediction APIs

### POST `/api/ai/predict-metadata`
Use AI to predict document metadata (subject, year, etc.) from file content.

- **Auth:** Required
- **Content-Type:** `multipart/form-data`
- **Request:** `file` field
- **Response:** `{ "success": true, "predicted": { "subject": "...", "year": ..., "department": "..." } }`

### POST `/api/ask-paper`
Ask a question about a document (AI-powered).

- **Auth:** Required
- **Request:** `{ "document_id": "uuid", "question": "text" }`
- **Response:** `{ "success": true, "answer": "text" }`

### POST `/api/extract-ocr`
Extract text from an uploaded image/PDF using OCR.

- **Auth:** Required
- **Request:** `multipart/form-data` with `file`
- **Response:** `{ "success": true, "text": "..." }`

---

## 9. Chat APIs

### GET `/chat`
Chat landing page.

- **Auth:** Required

### GET `/chat/<peer_id>`
Open a chat with a specific peer.

- **Auth:** Required

### POST `/api/chat/send`
Send a chat message (Socket.IO).

- **Auth:** Required (via Socket.IO session)
- **Event:** `send_message`
- **Payload:** `{ "peer_id": "uuid", "message": "text" }`

### GET `/api/chat/request-history`
Fetch chat history for a peer.

- **Auth:** Required
- **Query params:** `peer_id`

### GET `/api/chat/resend-history`
Resend missed messages.

- **Auth:** Required

### GET `/api/chat/online`
Check if a user is online.

- **Auth:** Required
- **Query params:** `user_id`
- **Response:** `{ "success": true, "online": bool }`

### GET `/api/chat/user-info/<user_id>`
Get chat user info.

- **Auth:** Required

### GET `/api/chat/search-peers`
Search for chat peers.

- **Auth:** Required
- **Query params:** `q=<search>`

---

## 10. MemoryWall APIs

### GET `/memorywall`
MemoryWall dashboard.

- **Auth:** Required

### GET,POST `/memorywall/create`
Create a new MemoryWall.

- **Auth:** Required

### GET `/m/<slug>`
View a public MemoryWall.

- **Auth:** None

### GET `/memorywall/reveal/<wall_id>`
Reveal memory wall stats.

- **Auth:** Required (owner only)

### POST `/api/memorywall/submit`
Submit a friend response to a wall.

- **Auth:** None
- **Rate limit:** 5 per IP per hour (SHA256 hashed IP)
- **Request:** See MemoryWall feature docs

### POST `/api/memorywall/upload-signature`
Upload a signature PNG.

- **Auth:** None
- **Content-Type:** `multipart/form-data`
- **Field:** `signature`
- **Max size:** 512KB, PNG/JPEG only

### GET `/api/memorywall/stats/<wall_id>`
Get wall statistics (owner only).

- **Auth:** Required

---

## 11. Store Room APIs

### GET `/store-room`
Store room main page.

- **Auth:** Required

### POST `/store-room/api/label`
Label a file in store room.

- **Auth:** Required
- **Request:** `{ "file_id": "uuid", "label": "string" }`

### POST `/store-room/api/sync`
Sync store room data.

- **Auth:** Required

### GET `/store-room/api/unlabeled`
Get unlabeled files in store room.

- **Auth:** Required

### POST `/store-room/api/rename-file`
Rename a file in store room.

- **Auth:** Required
- **Request:** `{ "file_id": "uuid", "new_name": "string" }`

### POST `/store-room/api/verify`
Verify a file in store room.

- **Auth:** Required

### GET `/store-room/api/verification-queue`
Get verification queue.

- **Auth:** Required

---

## 12. Quota & Subscription APIs

### GET `/api/quota`
Get current user's paper quota.

- **Auth:** Required
- **Response:** `{ "success": true, "quota_remaining": int, "last_reset": "YYYY-MM" }`

### POST `/api/waitlist/join`
Join the waitlist for premium access.

- **Auth:** None
- **Request:** `{ "email": "...", "college_id": "..." }`

### POST `/api/request-material`
Request a specific material from other users.

- **Auth:** Required
- **Request:** `{ "subject_id": "...", "title": "...", "description": "..." }`

### GET `/api/material-requests`
Get material requests for the current user.

- **Auth:** Required

### POST `/api/material-request/respond`
Respond to a material request.

- **Auth:** Required
- **Request:** `{ "request_id": "uuid", "response": "text" }`

### GET `/api/user/<target_user_id>/materials`
Get materials uploaded by a specific user.

- **Auth:** Required

---

## 13. Notification APIs

### GET `/api/my-notifications`
Get user's notifications.

- **Auth:** Required
- **Response:** `{ "success": true, "notifications": [...] }`

### POST `/api/my-notifications/read`
Mark all notifications as read.

- **Auth:** Required

---

## 14. Event Tracking APIs

### POST `/api/events`
Track a user event (for analytics).

- **Auth:** Required
- **Request:** `{ "event": "string", "data": {...} }`

---

## 15. Push Notification APIs

### POST `/api/push/subscribe`
Subscribe device to push notifications.

- **Auth:** Required
- **Request:** `{ "endpoint": "string", "keys": { "p256dh": "string", "auth": "string" } }`

### POST `/api/push/send` (Admin only)
Send push notification to users.

- **Auth:** Admin required

---

## 16. PWA & Static APIs

### GET `/manifest.json`
PWA manifest file.

- **Auth:** None

### GET `/sw.js`
Service worker file.

- **Auth:** None

### GET `/favicon.ico`
Favicon.

- **Auth:** None

---

## 17. Utility APIs

### GET `/`
Homepage dashboard.

- **Auth:** None

### GET `/api/widget-data`
Data for homepage widgets.

- **Auth:** None

### POST `/api/contact`
Contact form submission.

- **Auth:** None
- **Request:** `{ "name": "...", "email": "...", "message": "..." }`

---

## 18. Profile Peer APIs

### GET `/profile/<user_id>`
View another user's public profile.

- **Auth:** Required

---

## Security

| Measure | Detail |
|---------|--------|
| CSRF | Flask-WTF, `WTF_CSRF_ENABLED=True` for form POSTs |
| Rate Limiting | Manual IP-hash check via Supabase query |
| Input Validation | Server-side `.strip()` and length enforcement |
| Spam Protection | Honeypot field `_honey` on public forms |
| File Validation | MIME check + PIL.Image.verify() |
| Ownership Check | Server fetches by `user_id` from session |
| Audit Logging | `log_security_audit_event()` in supabase_helper.py |
