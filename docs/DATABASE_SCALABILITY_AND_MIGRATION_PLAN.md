# AbhiHub Database Scalability, Security & Migration Plan (Option 2)

> **Objective**: Systematically eliminate schema redundancies, enforce referential integrity (`uuid` vs `text`), secure leaking RLS policies, and introduce high-performance database views and stored procedures — executed in zero-downtime, non-destructive phases.

---

## 1. Safety Guardrails & Principles
- **No Drop First**: Never drop or alter an existing column until the replacement column is populated and verified.
- **Dual Compatibility**: Both old JSON-based logic and new typed relational columns must function simultaneously during transition.
- **Data Validation**: Audit and sanitize invalid string UUIDs before applying hard foreign key constraints.
- **Step-by-Step Executable SQL**: Each phase contains isolated, reversible SQL scripts.

---

## 2. Migration Phases Roadmap

| Phase | Focus Area | Risk Level | Data Impact | Deliverable |
|---|---|---|---|---|
| **Phase 1** | **RLS Security Hotfixes** | Low | None (Policy only) | `scripts/phase1_rls_security_hotfix.sql` |
| **Phase 2** | **Pricing & Metadata Columnization** | Low | Non-destructive backfill | `scripts/phase2_pricing_columns_and_backfill.sql` |
| **Phase 3** | **Foreign Keys & User ID Normalization (`text` ➔ `uuid`)** | Medium | Cast & constrain | `scripts/phase3_uuid_fk_normalization.sql` |
| **Phase 4** | **Performance Views & Trigger Counters** | Low | Adds views & triggers | `scripts/phase4_views_and_trigger_counters.sql` |
| **Phase 5** | **Python Supabase Integration Refactor** | Medium | Code update | Python route & helper optimizations |

---

## 3. Phase Breakdown & Execution Details

### Phase 1: Security & RLS Lockdown
* **Goal**: Close unrestricted anonymous access without touching table schemas.
* **Key Actions**:
  1. Revoke `crush_select_all`, `crush_insert_all`, `crush_delete_all` on `user_crushes`; enforce user-level privacy.
  2. Restrict `scoring_config` from public write access to service role / admin only.
  3. Clean duplicate policies on `viewer_failure_reports` and restrict `ai_usage_log`.
* **Execution Status**: `[READY TO RUN]`

---

### Phase 2: Pricing & Document Metadata Columnization
* **Goal**: Stop storing critical business data in unstructured `documents.description` strings.
* **Key Actions**:
  1. Add typed columns to `documents`:
     - `is_paid boolean DEFAULT false`
     - `price numeric(10,2) DEFAULT 0.00`
     - `seller_id uuid REFERENCES profiles(id) ON DELETE SET NULL`
     - `coupon_code text`
     - `coupon_discount int4`
  2. Run safe backfill function to parse existing JSON inside `documents.description` and populate the columns.
  3. Preserve original `documents.description` intact so legacy readers don't fail.
* **Execution Status**: `[PENDING]`

---

### Phase 3: Referential Integrity & ID Normalization
* **Goal**: Resolve `uuid` vs `text` mismatches across user-centric tables.
* **Target Tables**:
  - `creator_wallets` (`user_id`: `text` ➔ `uuid`)
  - `wallet_ledger` (`creator_id`: `text` ➔ `uuid`)
  - `credit_transactions` (`user_id`: `text` ➔ `uuid`)
  - `ai_practice_tests` (`creator_user_id`: `text` ➔ `uuid`)
  - `tarika_agent_state` (`user_id`: `text` ➔ `uuid`)
  - `user_ai_keys` (`user_id`: `text` ➔ `uuid`)
* **Key Actions**:
  1. Run sanity query to identify any orphaned or non-UUID strings.
  2. Alter column types safely: `ALTER TABLE ... ALTER COLUMN ... TYPE uuid USING user_id::uuid`.
  3. Add explicit `FOREIGN KEY (...) REFERENCES profiles(id)`.
* **Execution Status**: `[PENDING]`

---

### Phase 4: Database Views & Counter Triggers
* **Goal**: Offload complex Python joins and eliminate race-condition counter updates.
* **Key Actions**:
  1. **View `v_documents_catalog`**:
     - Joins `documents`, `subjects`, `departments`, `colleges`, and `profiles`.
     - Exposes all academic hierarchy and pricing details in 1 single fast query.
  2. **Automated Counter Triggers**:
     - Auto-increment/decrement `documents.view_count` on `document_views` insert.
     - Auto-calculate `like_count` on `document_votes` insert/update/delete.
     - Auto-maintain `bookmark_count` on `bookmarks` changes.
* **Execution Status**: `[COMPLETED - VERIFIED]`

---

### Phase 5: Python Application Layer Refactoring
* **Goal**: Connect Flask backend to leverage the new structured columns and views.
* **Key Actions**:
  1. Update `methods/supabase_helper.py` to query `v_documents_catalog`.
  2. Update `data/pricing.py` and `routes/payments.py` to directly read `documents.price` and `documents.is_paid`.
  3. Deprecate client-side JSON parsing of `documents.description`.
* **Execution Status**: `[COMPLETED - VERIFIED]`

---

### Phase 6: Admin Cloud Monitoring & View Security Grants
* **Goal**: Provide accurate database storage metrics via RPC and grant PostgREST roles read access.
* **Key Actions**:
  1. `get_db_size()` function in `abhihub` and `public` schemas.
  2. `GRANT SELECT ON abhihub.v_documents_catalog TO anon, authenticated, service_role`.
* **Execution Status**: `[COMPLETED - VERIFIED]`

---

## 4. Current Progress & Next Immediate Step
- [x] Full database audit and bottleneck discovery completed.
- [x] Multi-phase safe migration plan documented with explicit `abhihub` schema qualification.
- [x] **Phase 1 Executed (`abhihub`)**: [`scripts/phase1_rls_security_hotfix.sql`](file:///e:/Users/abhihub/New%20folder/abhihub/scripts/phase1_rls_security_hotfix.sql) — RLS security hotfixes applied.
- [x] **Phase 2 Executed (`abhihub`)**: [`scripts/phase2_pricing_columns_and_backfill.sql`](file:///e:/Users/abhihub/New%20folder/abhihub/scripts/phase2_pricing_columns_and_backfill.sql) — Monetization columns added & backfilled.
- [x] **Phase 3 Executed (`abhihub`)**: [`scripts/phase3_uuid_fk_normalization.sql`](file:///e:/Users/abhihub/New%20folder/abhihub/scripts/phase3_uuid_fk_normalization.sql) — UUID conversion & foreign keys applied.
- [x] **Phase 4 Executed (`abhihub`)**: [`scripts/phase4_views_and_trigger_counters.sql`](file:///e:/Users/abhihub/New%20folder/abhihub/scripts/phase4_views_and_trigger_counters.sql) — `v_documents_catalog` view and atomic triggers active.
- [x] **Phase 5 Completed**: Python codebase updated to leverage `v_documents_catalog`, relational pricing columns, and atomic triggers. All test suites passing.
- [x] **Phase 6 Completed**: [`scripts/phase6_admin_db_stats_rpc.sql`](file:///e:/Users/abhihub/New%20folder/abhihub/scripts/phase6_admin_db_stats_rpc.sql) — Live database size reporting (28.17 MB) & `v_documents_catalog` view permissions verified.

