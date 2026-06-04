# MemoryWall Security Model

## Authentication
| Route | Rule |
|---|---|
| `/memorywall`, `/memorywall/create`, `/memorywall/reveal/<id>` | `@auth_required` (session) |
| `/api/memorywall/stats/<id>` | `@auth_required` + ownership check |
| `/m/<slug>` | Public — no auth |
| `POST /api/memorywall/submit` | Public — rate limited |
| `POST /api/memorywall/upload-signature` | Public — file validated |

## IP Handling
- Raw IPs are **never stored**
- All IP tracking uses `SHA256(ip)` only
- Computed in `methods/know_me._hash_ip()`

## Rate Limiting
- Implemented via Supabase query (no Redis required)
- `memory_response` table queried for `ip_hash` count in last 1 hour
- Limit: **5 submissions per IP per hour**
- Returns HTTP 429 on breach

## Input Validation
| Field | Max Length | Server Enforced |
|---|---|---|
| friend_name | 50 | Yes (`.strip()[:50]`) |
| word_1/2/3 | 30 | Yes |
| memory_message | 500 | Yes |
| emoji | 20 | Yes |

## Spam Protection
- **Honeypot field** `_honey` — reject if non-empty (400)
- Hidden from users via `.km-hp { position:absolute; left:-9999px }` CSS

## CSRF
- Flask-WTF `WTF_CSRF_ENABLED = True` covers all POST forms globally
- API endpoints use JSON body (not form POST), which is not CSRF-vulnerable

## Signature Upload
- Accept: `image/png`, `image/jpeg` only (MIME check)
- Max size: 512 KB
- Server verifies with `PIL.Image.open().verify()`
- Rejects: SVG, executables, unknown MIME types

## Ownership Enforcement
- `/memorywall/reveal/<wall_id>`: server fetches wall by `user_id` from session, rejects if `wall.id != wall_id`
- `/api/memorywall/stats/<wall_id>`: same pattern, returns 403 if not owner

## Audit Logging
All errors logged via Python `logging.error()` with `[MemoryWall]` prefix.
Key events logged:
- Wall creation (INFO)
- Response submission (INFO)
- Signature upload failure (ERROR)
- Generator failure (ERROR)
- Firebase upload failure (WARNING)
