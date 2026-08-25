# Project Rules — AbhiHub

## Purpose
AbhiHub is a student-driven academic resource hub for engineering students to share and access study materials including notes, previous year questions (PYQs), practicals, and lab guides.

## Critical Rules (Never Violate)

### 1. PDF Viewer Rule
- **Never swap the PDF viewer library.** PDF.js is the canonical viewer, self-hosted at `static/pdfjs-6.1.200-dist/`.
- Preview in-page only — no download links, no `Content-Disposition: attachment`.
- `/pdf-proxy/` and `/api/view-doc/` must set `Content-Disposition: inline`, `X-Download-Options: noopen`, `no-store`, and a Referer check.
- Adobe Embed SDK may exist only as fallback, never primary.

### 2. App Directory Rule
- **Never create a directory named `app/` at the repo root.** It shadows `app.py` and silently 404s any route it lacks.
- To split `app.py` into a package, FIRST rename the entry point (e.g. `wsgi.py` with `gunicorn wsgi:app`) and update `Procfile`.

### 3. Authentication Rule
- `@auth_required` — session must exist. API paths get 401 JSON; pages redirect to `/login`.
- `@admin_required` — email must be in `ADMIN_EMAILS` (env var, empty list default).
- Never add auth bypasses without explicit rule approval.

### 4. Quota / Credit Rule
- Each upload grants `QUOTA_PER_UPLOAD` (19) paper opens; monthly reset.
- `_consume_credit()` gates every paper open. Admins bypass.
- `_check_and_log_view()` is the shared "check quota + log the view" helper — use it, don't re-implement.

### 5. No print() in Production
- `print()` is not allowed in `app.py`, `methods/`, `data/`.
- Use `logging.*` with appropriate levels (info, warning, error).

## Import Rules (Always Follow)

### 6. Top-Level Imports
- All module-level imports go at the top of the file.
- No inline `from methods.supabase_helper import X` inside route functions.
- Consolidate all `supabase_helper` imports to a single block at the top of `app.py`.

### 7. Import Deduplication
- One import per symbol at the top of each file.
- Deduplicate `init_supabase`, `storage`, `Image`, `datetime` — one import each.

### 8. No Bare `except:`
- Replace every bare `except:` with `except Exception as e: log.error(f"[context] {e}", exc_info=True); return {"success": False, "error": str(e)}`.

## Documentation Rules

### 9. Change Log Maintenance
- Maintain `.agent/logs/changes.log` and daily logs: `.agent/logs/YYYY-MM-DD.log`
- Each change records: Date, Time, Task, Action, Files affected, Result
- Use the lowest-cost suitable model for routine log maintenance.

### 10. Task Tracking
- Maintain `.agent/tasks/completed.md` and `.agent/tasks/ongoing.md`
- Allowed statuses: ONGOING, COMPLETED, INCOMPLETE, BLOCKED
- Never mark a task as COMPLETED unless work has actually been completed and verified.

### 11. Task History
- Every task performed must have a record inside `.agent/history/`
- Each task history record contains: Task, Task ID, Start Date, Last Worked Date, Status, Work Performed, Files Changed, Existing Code Reused, New Code Created, Dependencies Added, Important Decisions, Problems, Remaining Work

### 12. Memory System (Progressive)
Check memory levels in this order. Only move to the next level when the current level does not provide enough information:

1. **Flashcard** — High-value, frequently needed info: project purpose, architecture overview, technology stack, important paths, conventions, critical constraints, frequently used commands, key decisions
2. **Summary** — Feature summaries, architecture explanations, component relationships, implementation summaries, previous decisions, major workflows, current state of important features
3. **Important Notes** — Detailed technical info, configuration information, non-obvious behavior, known constraints, known problems, integration details, important technical decisions
4. **History** — Individual task records, previous implementations, completed/incomplete work, files changed, dates, problems encountered, previous approaches, remaining work

### 13. Minimum-Context Principle
Always use the smallest amount of information necessary:
- Directory inspection → Targeted search → Relevant file → Relevant section → Full file only when necessary

### 14. Code Reuse Priority
1. EXISTING PROJECT CODE
2. EXISTING PROJECT DEPENDENCY
3. SAFE & COMPATIBLE OPEN-SOURCE SOLUTION
4. NEW CODE (only when absolutely necessary)

### 15. Dependency Minimization
Before adding a dependency, ask: "Can this requirement be fulfilled using something already installed?"
- If yes: Use the existing dependency.
- If no: Determine whether a new dependency is actually necessary.

## Verification Rules

### 16. Pre-Deploy Verification
Before any deploy that touches routing:
```bash
python dev/route_parity.py verify  # confirm no route was lost
grep -rn "print(" app.py methods/ data/ --include="*.py"  # expect none (or only in tests)
```

### 17. Import Verification
```bash
python3 -c "from app import app"  # imports without error
```

### 18. PDF Viewer Integrity
Verify PDF.js self-hosted at `static/pdfjs-6.1.200-dist/` is intact and never swapped to Adobe Embed SDK as primary.

---
*Last updated: automatically recorded in .agent/logs/YYYY-MM-DD.log*