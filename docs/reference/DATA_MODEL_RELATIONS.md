# AbhiHub — Data Model Relation Graph

Generated: 2026-08-20  
Source: `app.py`, `data/*.py`, `methods/*.py`, `migrations/*.sql`, `ROUTES.md`, `ARCHITECTURE.md`  
Coverage: All Supabase tables, models, indexes, routes, and their relationships.

---

## 1. Table/Model Inventory

### Core Identity & Auth

| Table | Schema | Model File | Used By |
|-------|--------|-----------|---------|
| `profiles` | `abhihub` | `data/profiles.py` (Profile) | Auth, quota, dashboard, uploads, referrals |
| `students` | `public` | `data/profiles.py` (Student) | Profile completion, student-specific queries |
| `teachers` | `public` | `data/profiles.py` (Teacher) | Teacher profile queries |
| `user_sessions` | `abhihub` | `data/profiles.py` (UserSession) | Login/logout logging, analytics |

### Academic Taxonomy

| Table | Schema | Model File | Used By |
|-------|--------|-----------|---------|
| `colleges` | `abhihub` | `data/colleges.py` (College) | College pages, API, sitemap, waitlist |
| `departments` | `abhihub` | `data/colleges.py` (Department) | Department pages, API, subject filtering |
| `subjects` | `abhihub` | `data/colleges.py` (Subject) | Subject pages, API, document categorization |
| `college_departments` | `abhihub` | *(no model file — queried in `supabase_helper.py`)* | Department listing per college |
| `pending_subject_requests` | `abhihub` | *(no model file — queried in `supabase_helper.py`)* | Subject request workflow |
| `subject_aliases` | `abhihub` | *(no model file — used in `indexer.py`)* | Search tokenization |

### Content

| Table | Schema | Model File | Used By |
|-------|--------|-----------|---------|
| `documents` | `abhihub` | `data/documents.py` (Document) | All content routes, search, dashboard, store-room |
| `storage_assets` | `abhihub` | *(no model file — queried in `supabase_helper.py`)* | Store-room ingestion queue |
| `label_audit_logs` | `abhihub` | *(no model file — queried in `supabase_helper.py`)* | Audit trail for label actions |

### Interactions

| Table | Schema | Model File | Used By |
|-------|--------|-----------|---------|
| `document_votes` | `abhihub` | `data/interactions.py` (Vote) | Like/unlike toggle |
| `bookmarks` | `abhihub` | `data/interactions.py` (Bookmark) | Bookmark toggle |
| `document_comments` | `abhihub` | `data/interactions.py` (Comment) | Comment threads |
| `document_views` | `abhihub` | `data/interactions.py` (DocumentView) + `data/analytics.py` (DocumentView) | View logging, file access history |
| `file_access_history` | `abhihub` | *(no model file — queried in `supabase_helper.py`)* | Detailed file access log with email |

### Notifications & Push

| Table | Schema | Model File | Used By |
|-------|--------|-----------|---------|
| `notifications` | `abhihub` | `data/notifications.py` (Notification) | In-app notifications |
| `push_subscriptions` | `abhihub` | `data/notifications.py` (PushSubscription) | Web push delivery |

### Search (Migration 011)

| Table | Schema | Model File | Used By |
|-------|--------|-----------|---------|
| `search_documents` | `abhihub` | *(no model file — used in `indexer.py`, `search_api.py`)* | Pre-indexed search table |
| `search_manifest` | `abhihub` | *(no model file — used in `indexer.py`)* | Indexing version tracking |
| `search_analytics` | `abhihub` | *(no model file — used in `search_api.py`, `analytics_analyzer.py`)* | Search query feedback |

### Gamification (Migration 013)

| Table | Schema | Model File | Used By |
|-------|--------|-----------|---------|
| `contribution_logs` | `abhihub` | *(no model file — queried in `supabase_helper.py`)* | XP tracking, leaderboard |
| `user_achievements` | `abhihub` | *(no model file — queried in `supabase_helper.py`)* | Badge unlock tracking |
| `leaderboard_view` | `abhihub` | *(SQL VIEW — `migrations/014_leaderboard.sql`)* | Leaderboard aggregation |

### User Events (Migration 008)

| Table | Schema | Model File | Used By |
|-------|--------|-----------|---------|
| `user_events` | `abhihub` | *(no model file — used in `supabase_helper.py`)* | UPLOAD/DOWNLOAD/SUBJECT_REQUEST analytics |

### Memory Wall

| Table | Schema | Model File | Used By |
|-------|--------|-----------|---------|
| `memory_wall` | `abhihub` | `methods/know_me.py` | Memory wall CRUD |
| `memory_response` | `abhihub` | `methods/know_me.py` | Response submission |
| `signature` | `abhihub` | `methods/know_me.py` | Signature uploads |

### Other

| Table | Schema | Model File | Used By |
|-------|--------|-----------|---------|
| `colleges_waitlist` | `abhihub` | *(no model file — queried in `supabase_helper.py`)* | Waitlist signup |
| `material_requests` | `abhihub` | *(no model file — queried in `app.py`)* | Peer material request workflow |
| `user_file_views` | `abhihub` | *(no model file — queried in `app.py`, `supabase_helper.py`)* | Referred materials, analytics |
| `file_records` | `public` (?) | *(no model file — legacy)* | Upload notification tracking (legacy, see mg `add_upload_notification_columns.sql`) |

---

## 2. Relation Graph

### 2.1 Entity Relationship Diagram (text)

```
auth.users (Supabase Managed)
    │
    │ 1:1  (profiles.id = auth.users.id)
    ▼
profiles (abhihub) ─────────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    email, full_name, role, college_id → colleges.id, department_id → departments.id
    welcome_seen, last_donation_popup_at, last_feature_popup_at
    referral_code UNIQUE, referred_by → profiles.id
    referral_credits, referral_count, students_helped, reputation_score

    │ 1:N  (uploader_id)
    ▼
documents (abhihub) ─────────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    uploader_id → profiles.id
    college_id → colleges.id
    department_id → departments.id
    subject_id → subjects.id
    title, document_category, description (JSON text), file_url, file_type
    file_size_bytes, storage_provider, provider_public_id
    status (pending | approved | rejected)
    view_count, like_count, bookmark_count, comment_count
    exam_type, file_hash
    UNIQUE(storage_provider, provider_public_id)  [mg 010]
    INDEX idx_documents_file_hash                   [mg 012]
    INDEX idx_documents_exam_type                   [mg 009]

    │ 1:N  (document_id)
    ├────────────────────────────────────────────────────────────────────────────┐
    ▼                                                                              │
document_votes (abhihub) ──────────────────────────────────────────────────────────┤
    user_id → profiles.id                                                       ┘
    document_id → documents.id
    vote_type

bookmarks (abhihub) ───────────────────────────────────────────────────────────────┐
    user_id → profiles.id                                                       ┘
    document_id → documents.id

document_comments (abhihub) ───────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    document_id → documents.id
    user_id → profiles.id
    content, is_deleted, created_at

document_views (abhihub) ───────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    document_id → documents.id
    user_id → profiles.id
    accessed_at, ip_address, device_type

file_access_history (abhihub) ───────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    document_id, user_id → profiles.id, user_email (NOT NULL), accessed_at
    INDEX: accessed_at DESC, (user_id, accessed_at), (user_email, accessed_at)


── Academic Taxonomy ───────────────────────────────────────────────────────────────┐
colleges (abhihub) ────────────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    name, abbreviation, popular_name, aliases TEXT[]

    │ 1:N  (college_id)
    ▼
departments (abhihub) ───────────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    college_id → colleges.id
    name, abbreviation

college_departments (abhihub) ────────────────────────────────────────────────────────┐
    college_id → colleges.id  +  department_id → departments.id                          ┘
    PK (college_id, department_id)
    INDEX: department_id

    │ 1:N  (department_id)
    ▼
subjects (abhihub) ───────────────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    department_id → departments.id
    name, subject_code, semester CHECK(1-8)

    │ 1:N  (subject_id)
    ▼
subject_aliases (abhihub) ────────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    subject_id → subjects.id
    alias, priority
    INDEX: subject_id

pending_subject_requests (abhihub) ────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    user_id → profiles.id
    college_id → colleges.id, department_id → departments.id
    subject_name, subject_code, semester CHECK(1-8)
    status (pending | approved | rejected)
    reviewed_by → profiles.id
    approved_subject_id → subjects.id
    UNIQUE INDEX: (department_id, lower(subject_name)) WHERE status='pending'


── Content Infrastructure ────────────────────────────────────────────────────────────┐
storage_assets (abhihub) ──────────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    provider, provider_public_id UNIQUE
    filename, mime, public_url, status (PENDING|PROCESSING|LABELED|ERROR|DELETED)
    locked_by → auth.users.id, locked_until, uploaded_at, last_seen, created_at
    INDEX: status, (provider, provider_public_id)
    RLS: authenticated ALL

label_audit_logs (abhihub) ────────────────────────────────────────────────────────────
    id UUID PK                                                                 ┐
    user_id → auth.users.id                                                     ┘
    document_id → documents.id
    action, details JSONB, created_at
    RLS: authenticated ALL


── Notifications ──────────────────────────────────────────────────────────────────────
notifications (abhihub) ───────────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    user_id → profiles.id
    type, title, message, action_url, is_read, created_at

push_subscriptions (abhihub) ───────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    user_id → profiles.id
    endpoint UNIQUE, p256dh, auth, device_type, created_at
    ON CONFLICT(endpoint) upsert


── Search Architecture ────────────────────────────────────────────────────────────────
search_documents (abhihub) ────────────────────────────────────────────────────────────┐
    file_id UUID PK (= documents.id 1:1)                                         ┘
    source, subject_id → subjects.id, college_id → colleges.id, department_id → departments.id
    semester CHECK(1-8)
    normalized_title text, search_vector JSONB
    token_version, last_indexed, status (pending|indexing|ready|failed)
    INDEX: college_id, subject_id, status

search_manifest (abhihub) ──────────────────────────────────────────────────────────────
    file_id UUID PK → search_documents.file_id ON DELETE CASCADE                    ┐
    pipeline_version, tokenizer_version, ocr_version, embedding_version,            ┘
    alias_version, indexed_at, status

search_analytics (abhihub) ─────────────────────────────────────────────────────────────
    id UUID PK                                                                 ┐
    query NOT NULL, results_count, clicked_file_id, response_time_ms              ┘
    user_id → profiles.id, created_at


── Gamification ───────────────────────────────────────────────────────────────────────
contribution_logs (abhihub) ────────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    user_id → profiles.id
    action_type, entity_id, entity_type, xp_awarded, description, created_at
    INDEX: user_id, created_at

user_achievements (abhihub) ────────────────────────────────────────────────────────────
    id UUID PK                                                                 ┐
    user_id → profiles.id                                                       ┘
    badge_name UNIQUE per user, badge_icon, unlocked_at
    UNIQUE(user_id, badge_name)
    INDEX: user_id

leaderboard_view (VIEW) ────────────────────────────────────────────────────────────────
    SELECT p.id, p.full_name, p.email, p.college_id,
           COALESCE(p.reputation_score,0) + COALESCE(SUM(c.xp_awarded),0) AS total_xp,
           p.students_helped
    FROM profiles p LEFT JOIN contribution_logs c ON p.id = c.user_id
    GROUP BY p.id, p.full_name, p.email, p.college_id, p.students_helped
    ORDER BY total_xp DESC


── User Events ─────────────────────────────────────────────────────────────────────────
user_events (abhihub) ───────────────────────────────────────────────────────────────────
    id UUID PK                                                                 ┐
    user_id → profiles.id                                                       ┘
    event_type CHECK IN ('UPLOAD','DOWNLOAD','SUBJECT_REQUEST')
    metadata JSONB, created_at
    INDEX: event_type, user_id, created_at DESC


── Memory Wall ────────────────────────────────────────────────────────────────────────
memory_wall (abhihub) ───────────────────────────────────────────────────────────────────┐
    id UUID PK                                                                 ┘
    user_id TEXT (not FK — string), slug UNIQUE, title, photo_url
    college, branch, graduation_year, status (active|closed)
    response_count, view_count, created_at, updated_at
    INDEX: user_id, slug

memory_response (abhihub) ──────────────────────────────────────────────────────────────
    id UUID PK                                                                 ┐
    wall_id → memory_wall.id ON DELETE CASCADE                                  ┘
    friend_name, word_1, word_2, word_3, memory_message, emoji
    anonymous, ip_hash, created_at
    INDEX: wall_id, (ip_hash, created_at)

signature (abhihub) ─────────────────────────────────────────────────────────────────────
    id UUID PK                                                                 ┐
    response_id → memory_response.id ON DELETE CASCADE                           ┘
    signature_url, created_at


── Other ───────────────────────────────────────────────────────────────────────────────
college_waitlist (abhihub) ──────────────────────────────────────────────────────────────
    id UUID PK                                                                 ┐
    college_id → colleges.id                                                    ┘
    email NOT NULL, name, created_at
    UNIQUE(college_id, email)
    INDEX: college_id
    RLS: anon INSERT, service_role SELECT

material_requests (abhihub) ─────────────────────────────────────────────────────────────
    id UUID PK                                                                 ┐
    requester_id → profiles.id, target_user_id → profiles.id                    ┘
    document_id → documents.id (?), message, status, created_at, responded_at

user_file_views (abhihub) ───────────────────────────────────────────────────────────────
    id UUID PK                                                                 ┐
    user_id → profiles.id, file_id → documents.id                              ┘
    created_at
    Used for: referred materials, analytics dashboards

file_records (public?) ───────────────────────────────────────────────────────────────────
    Legacy upload tracking table (see mg add_upload_notification_columns.sql)
    upload_notified, notified_at
    INDEX: (upload_notified, uploaded_at) WHERE upload_notified=FALSE


── Legacy / Public Schema ──────────────────────────────────────────────────────────────
students (public) ───────────────────────────────────────────────────────────────────────
    profile_id → profiles.id (effectively PK)
    registration_number, college_id, branch_id, user_role CHECK('student'|'teacher')
    pursuing_year, year_of_joining, profile_completed, updated_at
    INDEX: profile_id, (college_id, branch_id), profile_completed
    TRIGGER: update_students_timestamp

teachers (public) ───────────────────────────────────────────────────────────────────────
    profile_id → profiles.id (effectively PK)
    employee_id, designation, profile_completed
```

---

## 3. Index Registry (complete)

### Primary Keys

| Table | PK Type | Notes |
|-------|---------|-------|
| `profiles` | `id` UUID | = auth.users.id |
| `students` | `profile_id` (implicit) | no explicit PK constraint |
| `teachers` | `profile_id` (implicit) | no explicit PK constraint |
| `user_sessions` | `id` UUID | |
| `documents` | `id` UUID | |
| `document_votes` | (none explicit) | unique on (user_id, document_id) implied |
| `bookmarks` | (none explicit) | unique on (user_id, document_id) implied |
| `document_comments` | `id` UUID | |
| `document_views` | `id` UUID | |
| `colleges` | `id` UUID | |
| `departments` | `id` UUID | |
| `subjects` | `id` UUID | |
| `college_departments` | `(college_id, department_id)` composite | |
| `pending_subject_requests` | `id` UUID | |
| `subject_aliases` | `id` UUID | |
| `search_documents` | `file_id` UUID | |
| `search_manifest` | `file_id` UUID | |
| `search_analytics` | `id` UUID | |
| `contribution_logs` | `id` UUID | |
| `user_achievements` | `id` UUID | |
| `user_events` | `id` UUID | |
| `storage_assets` | `id` UUID | |
| `label_audit_logs` | `id` UUID | |
| `notifications` | `id` UUID | |
| `push_subscriptions` | `id` UUID | |
| `file_access_history` | `id` UUID | |
| `college_waitlist` | `id` UUID | |
| `memory_wall` | `id` UUID | |
| `memory_response` | `id` UUID | |
| `signature` | `id` UUID | |
| `material_requests` | `id` UUID | |
| `user_file_views` | `id` UUID | |

### Unique Constraints

| Table | Columns | Migration |
|-------|---------|-----------|
| `documents` | `(storage_provider, provider_public_id)` | mg 010 |
| `storage_assets` | `(provider, provider_public_id)` | mg 010 |
| `college_waitlist` | `(college_id, email)` | add_college_waitlist |
| `pending_subject_requests` | `(department_id, lower(subject_name))` WHERE status='pending' | mg 008 |
| `user_achievements` | `(user_id, badge_name)` | mg 013 |
| `profiles` | `referral_code` | mg 015 |
| `memory_wall` | `slug` | know_me_tables |
| `push_subscriptions` | `endpoint` | (upsert on_conflict) |

### Secondary Indexes

| Index Name | Table | Columns | Migration |
|------------|-------|---------|-----------|
| `idx_pending_subject_unique` | pending_subject_requests | (department_id, lower(subject_name)) | mg 008 |
| `idx_college_departments_dept` | college_departments | department_id | mg 008 |
| `idx_user_events_type` | user_events | event_type | mg 008 |
| `idx_user_events_user` | user_events | user_id | mg 008 |
| `idx_user_events_created` | user_events | created_at DESC | mg 008 |
| `idx_documents_exam_type` | documents | exam_type | mg 009 |
| `idx_storage_assets_status` | storage_assets | status | mg 010 |
| `idx_storage_assets_provider_id` | storage_assets | (provider, provider_public_id) | mg 010 |
| `idx_subject_aliases_subject_id` | subject_aliases | subject_id | mg 011 |
| `idx_search_docs_college` | search_documents | college_id | mg 011 |
| `idx_search_docs_subject` | search_documents | subject_id | mg 011 |
| `idx_search_docs_status` | search_documents | status | mg 011 |
| `idx_documents_file_hash` | documents | file_hash | mg 012 |
| `idx_contribution_logs_user_id` | contribution_logs | user_id | mg 013 |
| `idx_contribution_logs_created_at` | contribution_logs | created_at | mg 013 |
| `idx_user_achievements_user_id` | user_achievements | user_id | mg 013 |
| `idx_profiles_referral_code` | profiles | referral_code | mg 015 |
| `idx_profiles_referred_by` | profiles | referred_by | mg 015 |
| `idx_college_waitlist_college_id` | college_waitlist | college_id | add_college_waitlist |
| `idx_students_user_id` | students | profile_id | add_student_profile_fields |
| `idx_students_college_branch` | students | (college_id, branch_id) | add_student_profile_fields |
| `idx_students_profile_completed` | students | profile_completed | add_student_profile_fields |
| `idx_file_records_upload_notified` | file_records | (upload_notified, uploaded_at) WHERE upload_notified=FALSE | add_upload_notification_columns |
| `idx_file_access_user_id` | file_access_history | user_id | fix_file_access_history_rls |
| `idx_file_access_user_email` | file_access_history | user_email | fix_file_access_history_rls |
| `idx_file_access_accessed_at` | file_access_history | accessed_at DESC | fix_file_access_history_rls |
| `idx_file_access_user_time` | file_access_history | (user_id, accessed_at DESC) | fix_file_access_history_rls |
| `idx_file_access_email_time` | file_access_history | (user_email, accessed_at DESC) | fix_file_access_history_rls |
| `idx_memory_wall_user_id` | memory_wall | user_id | know_me_tables |
| `idx_memory_wall_slug` | memory_wall | slug | know_me_tables |
| `idx_memory_response_wall` | memory_response | wall_id | know_me_tables |
| `idx_memory_response_iphash` | memory_response | (ip_hash, created_at) | know_me_tables |

---

## 4. Route → Model Mapping

### Auth & Profile

| Route | Model(s) Used | Purpose |
|-------|--------------|---------|
| `/auth` (POST) | profiles, user_sessions | SSO login, profile upsert, session log |
| `/api/profile` (GET) | profiles | Get current user profile |
| `/api/profile/update` (POST) | profiles | Update profile fields |
| `/api/profile-status` (GET) | profiles | Check auth status |
| `/api/quota` (GET) | profiles | Get paper quota remaining |
| `/api/onboarding/status` | profiles | Check welcome_seen |
| `/api/onboarding/welcome-seen` | profiles | Mark welcome_seen=true |
| `/login`, `/signup`, `/reset-password` | profiles (indirect via Supabase) | Auth pages |
| `/dashboard` | profiles, documents, document_views | Dashboard with stats |

### Taxonomy / Discovery

| Route | Model(s) Used | Purpose |
|-------|--------------|---------|
| `/api/colleges` | colleges | List all colleges |
| `/api/branches` | departments | List all departments (branches) |
| `/api/departments` | departments | List departments |
| `/api/subjects` | subjects | List subjects, add subject |
| `/college/<slug>` | colleges, departments, subjects, documents | College landing page |
| `/college/<slug>/<dept>` | colleges, departments, subjects, documents | Department landing page |
| `/subject/<slug>` | subjects, documents | Subject page |
| `/api/waitlist/join` | college_waitlist | Join college waitlist |
| `/api/subject-request` | pending_subject_requests | Request a new subject |

### Content / Documents

| Route | Model(s) Used | Purpose |
|-------|--------------|---------|
| `/upload` | documents, storage_assets, profiles | Upload a document |
| `/preview` | documents, file_access_history, document_views | Preview a document (signed URL) |
| `/view_pdf` | documents, profiles | View PDF (legacy) |
| `/api/view-doc/<doc_id>` | documents | Serve document PDF |
| `/pdf-proxy/<path>` | documents | Proxy PDF from storage |
| `/api/recent-documents` | documents | Recent documents list |
| `/api/files/all` | documents | All approved documents |
| `/api/check-duplicate` | documents | Check for duplicate by hash |
| `/api/document-view` | document_views, file_access_history | Log a document view |
| `/api/file-access-history` | file_access_history | Get user's file access history |
| `/resource/<slug>` | documents, colleges, departments, subjects | Resource landing page |
| `/pyq` | documents | PYQ listing page |

### Interactions

| Route | Model(s) Used | Purpose |
|-------|--------------|---------|
| `/api/interactions/like` | document_votes, documents | Toggle like |
| `/api/interactions/bookmark` | bookmarks, documents | Toggle bookmark |
| `/api/interactions/comments/<doc_id>` | document_comments | Get/add comments |
| `/api/like` | document_votes, documents | Legacy like toggle |
| `/api/bookmark` | bookmarks, documents | Legacy bookmark toggle |

### Search

| Route | Model(s) Used | Purpose |
|-------|--------------|---------|
| `/api/v2/search` | search_documents, documents, subjects, colleges | Search documents |
| `/api/ai/predict-metadata` | (OpenRouter API) | Predict document metadata |
| `/api/ask-paper` | documents (PDF fetch), OpenRouter | AI Q&A on document |
| `/api/extract-ocr` | documents (PDF fetch), OpenRouter | OCR extract text |

### Dashboard / Admin

| Route | Model(s) Used | Purpose |
|-------|--------------|---------|
| `/dashboard` | profiles, documents, document_views, contribution_logs | Main dashboard |
| `/dashboard/search` | documents | Search within dashboard |
| `/dashboard/view` | documents (legacy p_view.html) | File viewer (legacy) |
| `/dashboard/share-receiver` | storage_assets (?) | PWA share target |
| `/store-room` | storage_assets, label_audit_logs, documents | Labeling queue dashboard |
| `/store-room/api/label` | storage_assets, documents, label_audit_logs | Label a paper |
| `/store-room/api/sync` | storage_assets | Sync storage assets |
| `/store-room/api/unlabeled` | storage_assets | Get unlabeled queue |
| `/store-room/api/rename-file` | storage_assets | Rename file |
| `/store-room/api/verify` | storage_assets, documents | Verify/approve |
| `/store-room/api/verification-queue` | storage_assets | Get verification queue |
| `/admin/*` routes | profiles, documents, notifications, push_subscriptions | Admin operations |

### Social / Peer

| Route | Model(s) Used | Purpose |
|-------|--------------|---------|
| `/chat` | (SocketIO) | Chat page |
| `/chat/<peer_id>` | (SocketIO) | Chat with peer |
| `/profile/<user_id>` | profiles, documents, user_file_views | Peer profile |
| `/api/user/<id>/materials` | documents, user_file_views | Peer's materials |
| `/api/request-material` | material_requests | Request material from peer |
| `/api/material-requests` | material_requests | Get material requests |
| `/api/material-request/respond` | material_requests | Respond to request |
| `/api/users/search` | profiles | Search users |

### Memory Wall

| Route | Model(s) Used | Purpose |
|-------|--------------|---------|
| `/memorywall` | memory_wall | Memory wall dashboard |
| `/memorywall/create` | memory_wall | Create a wall |
| `/m/<slug>` | memory_wall, memory_response | Public wall view |
| `/memorywall/reveal/<wall_id>` | memory_response | Reveal responses |
| `/api/memorywall/submit` | memory_response | Submit response |
| `/api/memorywall/upload-signature` | signature | Upload signature |
| `/api/memorywall/stats/<wall_id>` | memory_wall | Wall stats |

### Analytics

| Route | Model(s) Used | Purpose |
|-------|--------------|---------|
| `/api/events` | user_events | Track user event |
| `/admin/analytics` | document_views, documents, profiles, user_sessions | Analytics dashboard |

---

## 5. How Each Model Finds Something (detailed)

### profiles → "Find user by email/id, check quota, check role, find referrer"

- `Profile.get_by_id(user_id)` → `SELECT * FROM profiles WHERE id = <uuid>` — used by every `@auth_required` route
- `Profile.get_by_email(email)` → `SELECT * FROM profiles WHERE email = <email>` — used by auth callback
- `Profile.get_id_by_email(email)` → `SELECT id FROM profiles WHERE email = <email>` — used by all interaction toggles (vote, bookmark, comment, notification, push subscription)
- `Profile.upsert(user_id, email, full_name, role, college_id, department_id)` — used by `/auth` callback and profile update
- Quota: `profiles.paper_quota_remaining` + `last_quota_reset` → calculate remaining views
- Referral: `profiles.referral_code` (UNIQUE), `profiles.referred_by` → profiles.id, `profiles.referral_credits`, `profiles.referral_count`

### documents → "Find all approved docs, search by query/type/college/dept, find by uploader, find by file_url"

- `Document.get_all_approved(current_user_id)` → `SELECT *, profiles(...), subjects(...), document_votes(...), bookmarks(...) FROM documents WHERE status='approved' ORDER BY created_at DESC` — used by `/api/files/all`, dashboard, store-room
- `Document.search(query, document_type, college_id, department_id, year, limit)` → `SELECT *, profiles(...), subjects(...) FROM documents WHERE (document_category=?) AND (college_id=?) AND (department_id=?) AND (title ILIKE ? OR description ILIKE ?)` — used by legacy search
- `Document.get_by_uploader(user_id, limit)` → `SELECT *, profiles(...), subjects(...) FROM documents WHERE uploader_id = <uuid> ORDER BY created_at DESC LIMIT <n>` — used by profile page "my uploads"
- `Document.update_metadata(file_path, update_data)` → `SELECT id, description FROM documents WHERE file_url ILIKE '%<path>%' LIMIT 1` → then UPDATE — used by upload flow to patch metadata
- `get_document_by_id_rich(doc_id)` → `SELECT *, college:colleges(...), department:departments(...), subject:subjects(...), uploader:profiles!... FROM documents WHERE id = <uuid>` — used by `/api/view-doc/<id>`, `p_pdf_reader.html`
- `Document.calculate_ranks()` → `SELECT uploader_id, document_category, description, title FROM documents WHERE status='approved'` → compute points → used by leaderboard
- `save_file_record(...)` → INSERT into `documents` + `file_access_history` — used by upload flow

### colleges → "Find all colleges, find by slug (abbr/name/popular_name/aliases)"

- `College.get_all()` → `SELECT * FROM colleges ORDER BY name` — `/api/colleges`, sitemap
- `get_college_by_slug(slug)` → iterate all colleges, match abbreviation, name slug, popular_name slug, or aliases — `/college/<slug>`
- `get_colleges_by_brand(brand_slug)` → match popular_name or aliases — brand group pages
- `get_college_stats(college_id)` → count documents + traverse college_departments → departments → subjects to count subjects
- `get_recent_college_files(college_id, limit)` → `SELECT *, subject:subjects(name), uploader:profiles!... FROM documents WHERE college_id = <uuid> ORDER BY created_at DESC LIMIT <n>` — college page recent files

### departments → "Find all departments, find by college, find by slug"

- `Department.get_all()` → `SELECT * FROM departments ORDER BY name` — `/api/departments`, `/api/branches`
- `Department.get_by_college(college_id)` → `SELECT * FROM departments WHERE college_id = <uuid> ORDER BY name` — department listing per college page
- `get_department_stats(college_id, dept_id)` → count documents + subjects for completion %
- `get_recent_department_files(college_id, dept_id, limit)` → `SELECT *, subject:subjects(name), uploader:profiles!... FROM documents WHERE college_id = <uuid> AND department_id = <uuid> ORDER BY created_at DESC LIMIT <n>` — department page recent files

### subjects → "Find all subjects, find by department, find by slug, search by name"

- `Subject.get_all()` → `SELECT * FROM subjects ORDER BY name` — `/api/subjects`
- `Subject.get_by_department(dept_id)` → `SELECT * FROM subjects WHERE department_id = <uuid> ORDER BY name` — subject listing per department
- `get_subjects_by_slug(slug)` → iterate all subjects, match name slug → return IDs — `/subject/<slug>`, sitemap
- `Subject.search_by_name(name)` → `SELECT id FROM subjects WHERE name ILIKE '%<name>%' LIMIT 1` — upload flow subject lookup
- `get_subject_stats(subject_ids)` → `SELECT id FROM documents WHERE subject_id IN (<ids>)` — count docs per subject
- `get_recent_subject_files(subject_ids, limit)` → `SELECT *, college:colleges(...), uploader:profiles!... FROM documents WHERE subject_id IN (<ids>) ORDER BY created_at DESC LIMIT <n>` — subject page recent files

### document_votes → "Find if user already liked a document"

- `Vote.toggle_like(user_id, document_id)` → `SELECT * FROM document_votes WHERE document_id = <uuid> AND user_id = <uuid>` → if exists: DELETE + UPDATE documents.like_count - 1; else: INSERT + UPDATE documents.like_count + 1

### bookmarks → "Find if user bookmarked a document"

- `Bookmark.toggle(user_id, document_id)` → `SELECT * FROM bookmarks WHERE document_id = <uuid> AND user_id = <uuid>` → if exists: DELETE + UPDATE documents.bookmark_count - 1; else: INSERT + UPDATE documents.bookmark_count + 1

### document_comments → "Find comments for a document"

- `Comment.add(user_id, document_id, content)` → INSERT into document_comments
- `Comment.get_for_document(document_id)` → `SELECT id, content, created_at, user_id, profiles(full_name, role) FROM document_comments WHERE document_id = <uuid> AND is_deleted = false ORDER BY created_at ASC` — `/api/interactions/comments/<doc_id>`
- `Comment.add_by_email(user_email, document_id, content)` → resolve email → user_id → add

### document_views → "Find recent docs viewed by user, log a view"

- `DocumentView.log_view(user_id, document_id, ip_address, device_type)` → INSERT into document_views
- `DocumentView.get_recent_for_user(user_id, limit)` → `SELECT id, document_id, accessed_at, documents(id, title, subject_id, uploader_id, file_url, document_category) FROM document_views WHERE user_id = <uuid> ORDER BY accessed_at DESC LIMIT <n>` → dedup by document_id — used by file access history
- `DocumentView.log_view_by_email(user_email, ...)` → resolve email → log

### file_access_history → "Find detailed file access log with email"

- `save_file_record(...)` → INSERT into file_access_history (document_id, user_id, user_email, accessed_at)
- `/api/file_access_history` → `SELECT * FROM file_access_history WHERE user_id = <uuid> OR user_email = <email> ORDER BY accessed_at DESC`
- INDEX usage: `accessed_at DESC` for timeline, `(user_id, accessed_at DESC)` for user timeline, `(user_email, accessed_at DESC)` for email lookup

### storage_assets → "Find by provider+public_id (ingestion), find by status (labeling queue)"

- `/store-room/api/sync` → INSERT/UPSERT by (provider, provider_public_id) — UNIQUE constraint prevents duplicates
- `/store-room/api/unlabeled` → `SELECT * FROM storage_assets WHERE status IN ('PENDING', 'PROCESSING')`
- `/store-room/api/verify` → UPDATE status to 'LABELED'
- `log_label_audit(user_id, document_id, action, details)` → INSERT into label_audit_logs

### search_documents → "Find indexed docs by normalized_title (exact/substring/fuzzy/word match)"

- `execute_search(query, college_id)` → 3-tier:
  1. Exact/substring: `SELECT file_id, normalized_title, subjects(name,subject_code), college_id FROM search_documents WHERE status='ready' AND normalized_title ILIKE '%<query>%'`
  2. Fuzzy: replace spaces with `%` → ILIKE again
  3. Word match: split query into words, OR filter on each word ILIKE
- Then JOIN documents for full metadata: `SELECT *, profiles!..., subjects(name,subject_code), colleges(name) FROM documents WHERE id IN (<file_ids>)`
- Feed: `/api/v2/search`

### search_manifest → "Track indexing version per document"

- 1:1 with search_documents → pipeline_version, tokenizer_version, ocr_version, embedding_version, alias_version
- Used to know when re-indexing is needed after tokenizer changes

### search_analytics → "Capture search query feedback"

- `search_analytics_endpoint()` → INSERT (query, results_count, clicked_file_id, response_time_ms, user_id)
- Feed: self-improving search loop (future)

### subject_aliases → "Find aliases for a subject (search tokenization)"

- Indexer: `SELECT alias FROM subject_aliases WHERE subject_id = <uuid>` → add to token vector with weight 50

### notifications → "Find notifications for user, mark read"

- `Notification.create(user_id, type, title, message, action_url)` → INSERT
- `Notification.create_by_email(user_email, ...)` → resolve email → create
- `Notification.get_history(limit)` → `SELECT * FROM notifications ORDER BY created_at DESC LIMIT <n>`
- `Notification.mark_read(notification_id)` → UPDATE is_read=true
- Feed: `/api/my-notifications`, `/api/my-notifications/read`

### push_subscriptions → "Find push subs by user, get all for delivery"

- `PushSubscription.save(user_id, endpoint, p256dh, auth, device_type)` → UPSERT on conflict endpoint
- `PushSubscription.get_all()` → `SELECT *, profiles(email) FROM push_subscriptions` → dict of user_id → subscription
- `PushSubscription.remove_by_endpoint(endpoint)` → DELETE
- Feed: `push_api.py`, `push_notifications.py`

### contribution_logs → "Find contribution history for XP"

- INSERT on every contribution action
- Feed: `leaderboard_view` aggregation: `SUM(c.xp_awarded)`

### user_achievements → "Find badges for user"

- UNIQUE(user_id, badge_name) → prevents double-earning
- Feed: badge unlock logic

### leaderboard_view → "Find ranked users by total XP"

- SQL VIEW: `SELECT p.id, p.full_name, p.email, p.college_id, COALESCE(p.reputation_score,0) + COALESCE(SUM(c.xp_awarded),0) AS total_xp, p.students_helped FROM profiles p LEFT JOIN contribution_logs c ON p.id = c.user_id GROUP BY ... ORDER BY total_xp DESC`
- Feed: `/leaderboard` routes, `/dashboard` stats

### user_events → "Track UPLOAD/DOWNLOAD/SUBJECT_REQUEST events"

- `track_user_event(user_id, event_type, metadata)` → INSERT (fire-and-forget)
- INDEX: event_type for filtering, user_id for per-user queries, created_at DESC for timeline

### memory_wall → "Find memory walls by slug or user"

- `memorywall_public(slug)` → `SELECT * FROM memory_wall WHERE slug = <slug>` — `/m/<slug>`
- `memorywall_dashboard()` → `SELECT * FROM memory_wall WHERE user_id = <user_id>` — `/memorywall`
- `memorywall_create()` → INSERT
- `api_memorywall_submit()` → INSERT into memory_response + UPDATE memory_wall.response_count
- `api_memorywall_upload_signature()` → INSERT into signature
- `api_memorywall_stats(wall_id)` → SELECT response_count, view_count from memory_wall

### memory_response → "Find responses for a wall"

- `memorywall_reveal(wall_id)` → `SELECT * FROM memory_response WHERE wall_id = <uuid>` — `/memorywall/reveal/<wall_id>`

### signature → "Find signature for a response"

- `INSERT INTO signature (response_id, signature_url)` — `/api/memorywall/upload-signature`

### college_waitlist → "Find waitlist count per college, join waitlist"

- `get_waitlist_count(college_id)` → `SELECT COUNT(*) FROM college_waitlist WHERE college_id = <uuid>` — used by college stats
- `join_college_waitlist(college_id, email, name)` → INSERT (UNIQUE constraint on college_id+email prevents duplicates)

### pending_subject_requests → "Find pending subject requests, insert new request"

- `create_subject_request(user_id, college_id, department_id, subject_name, subject_code, semester)` → INSERT
- UNIQUE INDEX prevents duplicate pending requests for same dept+name

### material_requests → "Find material requests between users"

- `/api/request-material` → INSERT (requester_id, target_user_id, document_id, message)
- `/api/material-requests` → `SELECT * FROM material_requests` — list requests
- `/api/material-request/respond` → UPDATE status

### user_file_views → "Find referred materials, analytics"

- `/dashboard/` (premium handler) → `SELECT COUNT(*) FROM user_file_views WHERE user_id = <uuid>` — viewed count
- `get_user_uploaded_files()` → `SELECT file_id, created_at, documents(...) FROM user_file_views WHERE user_id = <uuid> ORDER BY created_at DESC LIMIT 15` — referred materials

### file_records → "Legacy upload notification tracking"

- `upload_notified`, `notified_at` — legacy, see mg `add_upload_notification_columns.sql`
- INDEX: `(upload_notified, uploaded_at) WHERE upload_notified=FALSE`

---

## 6. Auto-Update Mechanism

The relation graph at `docs/reference/DATA_MODEL_RELATIONS.md` is the canonical reference. To keep it updated after every agent change:

### 6.1 Verification Script

A script at `dev/verify_model_graph.py` scans the project and prints:
- All migrations (16 files)
- All CREATE TABLE statements
- All model files with their TABLE constants
- All CREATE INDEX / CREATE UNIQUE INDEX statements
- All CREATE VIEW statements
- All foreign key REFERENCES
- All `.table('...')` references in Python code

Run after every change:
```bash
python dev/verify_model_graph.py
```

### 6.2 Update Checklist (agent must follow)

After any change, the agent must:

1. **New migration SQL** → Add table to §1, relation to §2, indexes to §3
2. **New column** → Update §1 table description
3. **New index** → Add to §3 index registry
4. **New model file** (`data/*.py`) → Add to §1, update §4 route mapping
5. **New route** → Add to §4 route→model mapping, update §5 how model finds something
6. **New FK relationship** → Update §2 ER diagram
7. **New convenience wrapper** (email→id resolver) → Update §5
8. **Changed RLS** → Update §1 table notes
9. **Run `python dev/verify_model_graph.py`** to confirm no tables/indexes/routes were missed
10. **Re-read §3** against actual `migrations/*.sql` files

### 6.3 Source of Truth

- Tables: `migrations/*.sql` + any tables created via Supabase dashboard (not in migrations)
- Models: `data/*.py` class TABLE constants
- Routes: `app.py` @app.route decorators + `ROUTES.md`
- Indexes: `migrations/*.sql` CREATE INDEX statements
- Relationships: Foreign key REFERENCES in migrations + join patterns in `data/*.py` and `methods/*.py`

---

## 7. Notable Gaps / Observations

1. **`file_records`** — migration `add_upload_notification_columns.sql` references this table, but no CREATE TABLE found in migrations. May be a legacy table created outside migrations or in a different schema.
2. **`material_requests`** and **`user_file_views`** — heavily used in `app.py` and `supabase_helper.py` but no CREATE TABLE in any migration. Likely created via Supabase dashboard.
3. **`students`** and **`teachers`** are in the `public` schema, not `abhihub`. This is unusual — most tables are in `abhihub`.
4. **`push_subscriptions`** has no model file — all logic is in `data/notifications.py` (PushSubscription class).
5. **`storage_assets`**, **`label_audit_logs`**, **`search_documents`**, **`search_manifest`**, **`search_analytics`**, **`subject_aliases`**, **`pending_subject_requests`**, **`college_departments`**, **`file_access_history`**, **`contribution_logs`**, **`user_achievements`**, **`user_events`** — all have no dedicated model file. They are accessed directly via `client.table('...')` in `methods/supabase_helper.py` or other service files.
6. **`leaderboard_view`** is a SQL VIEW, not a table — created in `migrations/014_leaderboard.sql`.

---

*Document version: 1.0 — 2026-08-20*  
*Maintained by: every agent that touches the data layer*
