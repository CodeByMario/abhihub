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

## MemoryWall APIs

### POST `/api/memorywall/submit`
Submit a friend response to a wall.

- Auth: None required
- Rate limit: 5 per IP per hour (SHA256 hashed IP)

**Request:**
```json
{
  "wall_id": "uuid",
  "friend_name": "string (max 50)",
  "word_1": "string (max 30)",
  "word_2": "string (max 30)",
  "word_3": "string (max 30)",
  "memory_message": "string (max 500, optional)",
  "emoji": "string (max 20, optional)",
  "anonymous": false,
  "signature_url": "string (Firebase URL, optional)",
  "_honey": ""
}
```

**Responses:**
| Status | Body |
|---|---|
| 200 | `{ "success": true, "response_id": "uuid" }` |
| 400 | `{ "success": false, "message": "Missing required fields" }` |
| 429 | `{ "success": false, "message": "Too many submissions. Try again later." }` |

---

### POST `/api/memorywall/upload-signature`
Upload a signature PNG image.

- Auth: None required
- Content-Type: `multipart/form-data`
- Field name: `signature`
- Max size: 512KB, PNG/JPEG only, PIL-verified

**Response 200:**
```json
{ "success": true, "url": "https://storage.googleapis.com/..." }
```

**Response 400:**
```json
{ "success": false, "message": "Invalid file type" }
```

---

### GET `/api/memorywall/stats/<wall_id>`
Get wall statistics (owner only).

- Auth: Required

**Response 200:**
```json
{
  "success": true,
  "response_count": 12,
  "top_words": [
    { "word": "smart", "count": 5 },
    { "word": "funny", "count": 4 }
  ]
}
```

---

## Document Interaction APIs

### POST `/api/interactions/like`
Like a document.

- Auth: Required

**Request:**
```json
{ "document_id": "uuid" }
```

**Response:**
```json
{ "success": true, "like_count": 42 }
```

---

### POST `/api/interactions/bookmark`
Bookmark a document.

- Auth: Required

**Request:**
```json
{ "document_id": "uuid" }
```

**Response:**
```json
{ "success": true, "bookmarked": true }
```

---

## Quota API

### GET `/api/quota`
Get current user's paper quota.

- Auth: Required

**Response:**
```json
{
  "success": true,
  "quota_remaining": 15,
  "last_reset": "2026-05"
}
```

---

## Push Notification APIs

### POST `/api/push/subscribe`
Subscribe device to push notifications.

- Auth: Required

**Request:**
```json
{
  "endpoint": "string",
  "keys": {
    "p256dh": "string",
    "auth": "string"
  }
}
```

---

### POST `/api/push/send` (Admin only)
Send push notification to users.

- Auth: Admin required

---

## Store Room API

### POST `/store-room/api/label`
Label/categorize a store room file.

- Auth: Required

**Request:**
```json
{ "file_id": "uuid", "label": "string" }
```

---

## Security

| Measure | Detail |
|---|---|
| CSRF | Flask-WTF, `WTF_CSRF_ENABLED=True` for form POSTs |
| Rate Limiting | Manual IP-hash check via Supabase query |
| Input Validation | Server-side `.strip()` and length enforcement |
| Spam Protection | Honeypot field `_honey` on public forms |
| File Validation | MIME check + PIL.Image.verify() |
| Ownership Check | Server fetches by `user_id` from session |
| Audit Logging | `log_security_audit_event()` in supabase_helper.py |
