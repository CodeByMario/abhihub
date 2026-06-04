# MemoryWall Database Schema

## Schema: abhihub (Supabase)

### memory_wall
Stores one wall per user.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | gen_random_uuid() |
| user_id | TEXT NOT NULL | Firebase/Supabase auth UID |
| slug | TEXT UNIQUE NOT NULL | URL-safe, e.g. `abhijeet-k3m9x` |
| title | TEXT | Wall display name |
| photo_url | TEXT | Optional profile photo |
| college | TEXT | Optional |
| branch | TEXT | Optional |
| graduation_year | INTEGER | Optional |
| status | TEXT | 'active' or 'closed' |
| response_count | INTEGER | Denormalized counter |
| created_at | TIMESTAMPTZ | Default NOW() |
| updated_at | TIMESTAMPTZ | Updated on each submission |

### memory_response
One row per friend submission.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| wall_id | UUID FK → memory_wall.id | CASCADE DELETE |
| friend_name | TEXT NOT NULL | |
| word_1 | TEXT NOT NULL | max 30 chars |
| word_2 | TEXT NOT NULL | max 30 chars |
| word_3 | TEXT NOT NULL | max 30 chars |
| memory_message | TEXT | Optional, max 500 |
| emoji | TEXT | Optional, max 20 |
| anonymous | BOOLEAN | Default false |
| ip_hash | TEXT | SHA256 of IP, NEVER raw IP |
| created_at | TIMESTAMPTZ | |

### signature
Linked to a memory_response, stores Firebase URL.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| response_id | UUID FK → memory_response.id | CASCADE DELETE |
| signature_url | TEXT | Firebase Storage public URL |
| created_at | TIMESTAMPTZ | |

## Indexes
```sql
idx_memory_wall_user_id   ON memory_wall(user_id)
idx_memory_wall_slug       ON memory_wall(slug)
idx_memory_response_wall   ON memory_response(wall_id)
idx_memory_response_iphash ON memory_response(ip_hash, created_at)
```

## Important
- Run `migrations/know_me_tables.sql` in Supabase SQL editor
- Tables belong to `abhihub` schema
- Python client uses `ClientOptions(schema="abhihub")`
- Row Level Security (RLS) is disabled for these tables to allow secure operations proxying via the Flask backend
- Proper permissions are granted to `anon`, `authenticated`, and `service_role` roles for access through the schema API

