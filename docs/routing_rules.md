# AbhiHub Routing & URL Design Standards

## Core Rules
1. **Case**: All URL paths MUST be strictly lowercase (`/uhv`, not `/UHV`).
2. **Word Separation**: Use kebab-case for multi-word paths (`/file-updates`, `/user-transactions`).
3. **Collections**: Plural nouns for resource collections (`/api/documents`, `/api/subjects`).
4. **Single Entities**: Plural collection followed by identifier (`/api/documents/<doc_id>`).
5. **No Trailing Slash Drift**: Strict slash consistency (`/settings`, not `/settings/`).
6. **Redirects**: Deprecated/legacy URLs must issue HTTP 301 redirects to canonical targets via `routes/redirects.py`.
7. **HTTP Verbs**: REST conventions (GET for read, POST for create, PUT/PATCH for update, DELETE for remove).
8. **App Area Prefixes**:
   - Public: `/`, `/about`, `/contact`, `/college`
   - User App: `/app/...`, `/dashboard`, `/profile`, `/settings`
   - Admin: `/admin/...`
   - API: `/api/...` (or `/api/v1/...`)
