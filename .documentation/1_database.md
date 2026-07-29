# Database Documentation — AbhiHub

## Database Provider
- **Supabase** (PostgreSQL)
- Schema: `abhihub` (accessed via `ClientOptions(schema="abhihub")`)
- Auth schema: `auth` (managed by Supabase)
- Legacy public schema: `public` (used in older migrations)

---

## Schemas & Tables

### `abhihub` Schema (Main App)

| Table | Description |
|---|---|
| `colleges` | Registered colleges (name, abbreviation, city) |
| `departments` | Academic departments |
| `subjects` | Subjects linked to departments |
| `profiles` | Core user profile (role, email, name, subscription, reputation, rank) |
| `students` | Student-specific info (reg number, year, joining year) |
| `teachers` | Teacher-specific info (employee ID, designation) |
| `user_sessions` | Login/logout session tracking |
| `documents` | Uploaded files (title, category, url, status, view/like/bookmark counts) |
| `bookmarks` | User ↔ document bookmarks |
| `document_comments` | Comments on documents |
| `tags` | Document tags |
| `document_tags` | Many-to-many: documents ↔ tags |
| `document_views` | View tracking per document (IP, device) |
| `document_votes` | Upvote/downvote per document per user |
| `security_audit_logs` | Security events log |
| `push_subscriptions` | Web push notification endpoints |
| `notifications` | In-app notifications |
| `memory_wall` | Know Me / MemoryWall walls (slug, college, branch, grad year) |
| `memory_response` | Friend responses (3 words, message, emoji, anonymous) |
| `signature` | Signature images linked to responses |

---

### `public` Schema (Legacy / Migrations)

| Table | Description |
|---|---|
| `college` | Legacy college table |
| `students` | Legacy students table |
| `branch` | Branch/department table |
| `subject` | Subject table |
| `cae1`, `cae2`, `cae3` | CAE exam paper records |
| `ese` | End Semester Exam records |
| `file_access_history` | File access log (email, filename, url) |
| `file_records` | Uploaded file records (Cloudinary-linked) |

---

## Key Relationships

```
auth.users
  └── abhihub.profiles (1:1)
        ├── abhihub.students (1:1)
        ├── abhihub.teachers (1:1)
        ├── abhihub.documents (1:many, uploader)
        ├── abhihub.bookmarks (1:many)
        ├── abhihub.notifications (1:many)
        └── abhihub.memory_wall (1:1)
              └── abhihub.memory_response (1:many)
                    └── abhihub.signature (1:1)

abhihub.colleges → abhihub.profiles (college_id)
abhihub.departments → abhihub.subjects → abhihub.documents
```

---

## Enums (User-Defined Types)

| Type | Values |
|---|---|
| `user_role` | `student`, `teacher`, `admin` |
| `subscription_tier` | `free`, `premium` |
| `verification_state` | `pending`, `approved`, `rejected` |
| `storage_provider` | `cloudinary`, `firebase` |
| `notification type` | (various event types) |

---

## Connection

```python
# methods/supabase_helper.py
from supabase import create_client, ClientOptions

client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
    options=ClientOptions(schema="abhihub")
)
```

---

## Quota System

- `profiles.paper_quota_remaining` — default 19 per user
- `profiles.last_quota_reset` — tracks monthly reset (e.g. `"2026-05"`)
- Reset logic handled server-side on quota API calls

---

## Migration Files

| File | Purpose |
|---|---|
| `migrations/008_all_features.sql` | Full feature migration |
| `migrations/add_quota_fields.sql` | Adds quota columns to profiles |
| `migrations/add_student_profile_fields.sql` | Student profile fields |
| `migrations/add_upload_notification_columns.sql` | Upload notification columns |
| `migrations/fix_file_access_history_rls.sql` | RLS fix for file history |
| `migrations/know_me_tables.sql` | MemoryWall/Know Me tables |
