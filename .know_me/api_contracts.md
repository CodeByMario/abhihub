# MemoryWall API Contracts

## POST /api/memorywall/submit
No auth required. Rate limited: 5 per hour per IP hash.

### Request Body (JSON)
```json
{
  "wall_id":       "uuid",
  "friend_name":   "string (max 50)",
  "word_1":        "string (max 30, required)",
  "word_2":        "string (max 30, required)",
  "word_3":        "string (max 30, required)",
  "memory_message":"string (max 500, optional)",
  "emoji":         "string (max 20, optional)",
  "anonymous":     false,
  "signature_url": "string (Firebase URL, optional)",
  "_honey":        ""
}
```
### Response 200
```json
{ "success": true, "response_id": "uuid" }
```
### Response 429
```json
{ "success": false, "message": "Too many submissions. Try again later." }
```
### Response 400
```json
{ "success": false, "message": "Missing required fields" }
```

---

## POST /api/memorywall/upload-signature
Multipart form, field name: `signature` (PNG, max 512KB)

### Response 200
```json
{ "success": true, "url": "https://storage.googleapis.com/..." }
```
### Response 400
```json
{ "success": false, "message": "Invalid file type" }
```

---

## GET /api/memorywall/stats/<wall_id>
Auth required. Owner only.

### Response 200
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
