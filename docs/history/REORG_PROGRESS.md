# Reorganization Progress Log

Single source of truth for what is done / pending. Update after every step.

## Ground rules discovered
- `Procfile`: `gunicorn app:app` → Python resolves `import app`.
- A directory named `app/` with `__init__.py` **SHADOWS** `app.py`.
  Never let an incomplete `app/` package exist at repo root.
- `app.py` currently holds **155 routes** and is the live entry point.

---

## STEP 1 — Neutralize production risk ✅ DONE
The `app/` package created earlier shadowed `app.py` while covering only
64 of 155 routes. Deploying would have 404'd 86 routes (`/`, `/pyq`,
`/profile`, `/account`, `/store-room`, `/leaderboard`, ...).

Action: moved `app/` → `.wip/app_package_incomplete/`, added `.wip/` to
`.gitignore`. Verified `import app` → `app.py` again.

---

## STEP 2 — Choose the target layout (decision, no code) ⬜ NEXT
Two viable options:

**Option A — `app.py` stays the single module (LOW RISK)**
- Keep 155 routes where they are.
- Add section banners + a route index at the top of `app.py`.
- Write `ARCHITECTURE.md` describing roles.
- Move dev tooling to `dev/`.
- Zero routing risk; file stays 5.7k lines.

**Option B — real package split (HIGH RISK, HIGH REWARD)**
- Rename entry to `wsgi.py` (`gunicorn wsgi:app`) so `app/` can exist.
- Move all 155 routes into `app/routes/*.py` blueprints.
- Requires a route-parity test before deploy.

Recommendation: **Option B but staged**, with parity gate after each move.

---

## STEP 3 — Route parity harness ✅ DONE
`dev/route_parity.py` + `dev/route_snapshot.json` (150 rules).
- `python dev/route_parity.py snapshot` → write baseline
- `python dev/route_parity.py verify`   → fail if any rule disappears

Static AST parse, so it runs with no env vars / DB / broken local
`flask_socketio`. **Proven**: temporarily commenting out `/leaderboard`
made verify exit 1 and name the missing rule; restore returned PASS.

## STEP 4 — Dev tooling → `dev/` ✅ DONE
- `bots/` → `dev/bots/`, `scripts/` → `dev/scripts/` (via `git mv`).
- Fixed `dev/bots/config.py` `.env` lookup (was parent-of-parent, now
  three levels up) — would otherwise have silently lost credentials.
- Fixed `dev/bots/run.py` `ROOT` (same off-by-one-level bug).
- Rewrote stale `bots/…` / `scripts/…` help strings in 7 files.
- Updated `docs/COMPANY_SKILLS_AND_BOTS.md` run commands.
- Verified `dev/bots/config.py` imports and `REPORTS_DIR` resolves.
- Route parity: PASS.

Left in place on purpose: `.ai/ .agents/ .record/ .codegraph/
.documentation/ .know_me/` — already dot-hidden; moving them is churn
with no readability gain. Their roles get documented in ARCHITECTURE.md.

## STEP 5 — ARCHITECTURE.md ✅ DONE
`ARCHITECTURE.md` at repo root. Contents:
- **Entry point warning** — why a root `app/` package must never exist
  (it shadows `app.py` and silently 404s every route it lacks).
- Layer diagram + role table (`app.py` web / `methods/` services /
  `data/` models / `cache_manager` / `templates` / `static` / `dev`).
- `app.py` route-cluster map by line band, so any route is findable.
- Per-file role tables for `methods/` and `data/`.
- Cross-cutting rules: anti-piracy, auth, quota, config, logging.
- "Common tasks" and "verify before deploy" sections.

Every factual claim in it was verified against the code, not assumed —
that process is what surfaced the M6 gap below.

## STEP 5b — M6 correction (print → logging) ✅ DONE
Earlier "M6 done" was **only true for `app.py`**. Verification while
writing ARCHITECTURE.md found **97 `print()` calls still live** across
12 production files (`methods/supabase_helper.py` alone had 59).

Converted all 97 with level inference (error/warn/info from message
content), added missing `import logging`, hand-fixed one bad insertion
in `methods/get_user_uploaded_files.py` (file had no import block).

Verified: all files parse; `import logging` present everywhere needed;
**0** `print()` left in `app.py` + `methods/` + `data/`; diffs contain
logging conversions and nothing else; route parity PASS.

## STEP 6 — M1 helper extraction ✅ DONE
Investigated the real duplication instead of trusting the earlier note.
Finding: the live `pdf_proxy` has **no** quota/logging block (that only
existed in the shelved package). The genuine duplication was the
extension→file-type dict plus `save_file_access` wiring repeated in
`/preview`, `/view_pdf` and `/resource/<slug>`.

Added to `app.py`:
- `_FILE_TYPE_BY_EXT` + `detect_file_type()` — one source of truth for
  extension→type mapping.
- `log_document_view()` — single view-logging contract; never raises, so
  a logging failure can't break document delivery.

Refactored all 3 call sites. `save_file_access` now appears only inside
the helper and in the API route that needs its return value.
Route parity: PASS.

## STEP 7 — Dead file removal ✅ DONE
Classified every root `.py` by evidence (imports, references, git age)
rather than by guesswork.

**Root `.py`: 23 → 7 files.**
- Kept 7 runtime modules: `app.py`, `cache_manager.py`, `push_api.py`,
  `push_notifications.py`, `scheduled_tasks.py`, `firebase_config.py`,
  `sync_firebase_documents.py`.
- `generate_vapid.py` → `dev/scripts/` (real reusable utility).
- 12 one-off migration/injection scripts → `trash/root_scripts/`
  (`inject_*`, `append_*`, `move_css`, `fix_api_reduction`,
  `search_lines`, `config_csrf`, `update_icons`, both security scanners —
  the scanners had hardcoded absolute paths, i.e. throwaway).
- 3 root test files → `tests/` (now 5 tests in one place).

**Other removals**
- `node_modules/`: **3,141 files were committed to git.** Untracked and
  gitignored; only tailwind/jsdom build tooling, reproducible from
  `package-lock.json`. Local copy untouched.
- `static/static/`: orphaned duplicate of an image that already exists at
  `static/premium/images/` (verified the template resolves to the real
  path) — removed.
- 475 `__pycache__` directories cleaned.

**🔴 PII leak found and stopped**
`exports/*.csv` were **tracked in git containing real student PII** —
names + institutional student emails (`users_active.csv`, `send_log.csv`,
5 more). Untracked and added `exports/` + `*.csv` to `.gitignore`.
Swept every remaining tracked file: only placeholders
(`john@example.com`) and official support addresses remain.

> **PURGED (this session):** the PII was confined to 22 **unpushed**
> commits — it never reached GitHub. Verified with
> `git log origin/Memory-wall -- exports/` (empty). Rewrote the unpushed
> range with `git filter-branch --index-filter` to drop `exports/`
> entirely, after taking a `backup-before-pii-purge` safety branch.
> Confirmed zero `exports/` entries across all 22 rewritten commits.

**Test infrastructure**
Added `tests/conftest.py` — puts repo root on `sys.path` and sets dummy
env vars, so `from app import app` works from any invocation directory.
Without it the two moved tests would have failed after relocation.

## STEP 8 — Markdown organisation ✅ DONE
124 `.md` files existed; 11 were loose at the repo root. Reorganised the
**curated** docs by purpose and left tooling-internal notes with their
tooling.

**Root: 11 → 4 files** (only what GitHub surfaces specially):
`README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`.

**New `docs/` tree** — folder name states whether it is current truth:

| Folder | Purpose | Current truth? |
|---|---|---|
| `architecture/` | how it's built | yes |
| `guides/` | how to do X | yes |
| `reference/` | exhaustive lookups | yes |
| `product/` | intent | intent only |
| `history/` | point-in-time snapshots | no — never edit |

Moves: `ARCHITECTURE.md`→`architecture/`; `ROUTES.md`,`BUGS.md`→
`reference/`; `FILE_HISTORY_SETUP.md`,`GA4_IMPLEMENTATION.md`,
`USER_GUIDE.md`,`COMPANY_SKILLS_AND_BOTS.md`→`guides/`; `IDEA.md`→
`product/`; `audit_report.md` (renamed `audit_report_2026-07-11.md`),
`ANALYTICS_CHANGES.md`,`CSS_CONFLICTS_RESOLVED.md`,`REORG_PROGRESS.md`→
`history/`.

**🔴 README.md was not a README.** It contained a CSS-pipeline summary
with copy-paste artifacts ("Copy", "@Pin Context", "Rules") — the repo's
front door for anyone arriving from GitHub. Preserved the content as
`docs/architecture/CSS_PIPELINE.md` and wrote a real README: what
AbhiHub is, stack table, quick start, verified env-var table, project
layout, the `app/`-shadowing warning, a documentation index, dev
commands, licence. Every claim checked against the repo (LICENSE,
`migrations/`, `.env.example`, `npm run build:css` all confirmed present).

**Added `docs/README.md`** — index mapping each doc to "read it when…",
plus conventions (new docs go in the purpose folder; never edit
`history/`; use relative links; root stays at 4 files).

**Link integrity:** added `dev/check_doc_links.py`, which validates every
relative markdown link and exits 1 on a broken one. **47 links checked —
all resolve.** Fixed the links the moves broke, pointed CONTRIBUTING at
ARCHITECTURE, updated ARCHITECTURE's own `docs/` row and tooling table,
and corrected a stale `BUGS.md` path in `dev/bots/roles/product.py`.

Left co-located on purpose: `static/css/pipeline/MIGRATION.md` and
`data/cache/README.md` (they document adjacent code) — both indexed.

## STEP 9 — P4 doc updates ✅ DONE
Rather than editing statuses from memory, wrote `dev/verify_bugs.py` which
checks all 28 `BUGS.md` items against the actual code and prints evidence.
First run: **24 fixed / 4 open** — so four items I'd have marked done were
not.

Closed three of them:
- **M9** — 5 `traceback.print_exc()` sites in `supabase_helper.py` had
  inline imports *and* wrote stack traces to stderr, bypassing logging
  entirely. Replaced with `logging.error(..., exc_info=True)`.
- **M11** — hardcoded `'2025'` year fallback → `datetime.now().year`.
- **L2** — documented in `SECURITY.md` that the Supabase anon key is
  publishable by design and that **RLS is the real security boundary**, so
  a missing RLS policy on a new table is a security bug. Also documented
  that `exports/` holds user data and must never be committed.

Also fixed a **false positive in my own checker**: its regex flagged the
legitimate module-level `import traceback` in `app.py` as inline. Fixed
the checker, not the code.

**M3 deferred with reasoning, not skipped.** `app.py` imports from
`methods.supabase_helper` inside ~91 route bodies. Verified there is no
circular import and no expensive import-time work, so the lazy imports are
stylistic rather than load-bearing — but hoisting 59 distinct symbols
touches nearly every route for zero functional gain. Documented in
`BUGS.md` as deferred, to revisit only if `app.py` is ever split into
blueprints.

Final: **27 fixed / 1 deliberately deferred.**

`BUGS.md` now opens with a verified status table plus three new sections:
why M3 is deferred, findings investigated and dismissed (anon key, the
non-existent `static/app.js`), and issues found during this pass that were
never in the original audit (the PII leak, tracked `node_modules`, the
README that wasn't a README).

`CHANGELOG.md` — added a full `[Unreleased]` entry with a `Security`
section leading on the PII purge. Also repaired pre-existing malformed
`||-` bullets that were rendering as broken table rows.

---

## Completed earlier (content fixes, verified)
- H1-H6 security fixes (bare except, auth decorators, ADMIN_EMAILS,
  CSRF TTL, CORS wildcards, `cors.py` deleted).
- M1-M15 quality fixes (view helper, device-type consolidation, logging
  instead of print, inline imports hoisted, O(1) rank, single-pass
  categorization, SocketIO CORS locked down, input length validation).
- L4 Turnstile sitekey → env var (4 templates + `app.py`).
- L5 ROUTES.md dead routes relabelled.
- L6 `|tojson|safe` → `|tojson` (2 templates).
- L7 CSS doc → `docs/CSS_CONFLICTS_RESOLVED.md`.
- L8 `print()` → `logging` in `methods/supabase_helper.py`.
- `.env.example` / `firebase_config.py` fully placeholdered.
- `SECURITY.md`, `.python-version` added; `runtime.txt` removed.
