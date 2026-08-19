# AbhiHub — Architecture

Role map for humans and bots. Read this before changing anything.

AbhiHub is a **Flask monolith** that serves engineering study material
(previous-year papers, notes, practicals) to students. Documents are
previewed **in-browser only** — never downloaded.

---

## 1. Entry point — read this first

```
Procfile:  web: gunicorn -k geventwebsocket...GeventWebSocketWorker -w 1 app:app
                                                                        ^^^^^^^^
                                                                        app.py : app
```

`gunicorn app:app` means Python runs `import app` and takes the `app`
attribute.

> **HARD RULE — do not create a directory named `app/` at the repo root.**
> A package `app/__init__.py` **shadows** `app.py`. Python prefers the
> package, so gunicorn would silently serve the package instead of
> `app.py`. If the package is incomplete, every route it lacks becomes a
> production 404 with no error at boot.
>
> To split `app.py` into a package you must FIRST rename the entry point
> (e.g. `wsgi.py` with `gunicorn wsgi:app`) and update `Procfile`.

---

## 2. Layer map — what plays what role

```
                    HTTP request
                         │
                    ┌────▼─────┐
                    │  app.py  │  routing + request/response + auth gates
                    │ (5.7k L) │  155 routes — THE web layer
                    └────┬─────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     ┌────▼────┐   ┌─────▼─────┐  ┌─────▼──────┐
     │ methods/│   │   data/   │  │cache_manager│
     │ services│   │  models   │  │  L1/L2/L3   │
     └────┬────┘   └─────┬─────┘  └────────────┘
          │              │
          └──────┬───────┘
                 │
        ┌────────▼─────────┐
        │ Supabase (schema │  Postgres + RLS + auth
        │    "abhihub")    │
        └──────────────────┘
        ┌──────────────────┐
        │   Cloudinary     │  file storage (canonical)
        │ Firebase Storage │  legacy, optional
        └──────────────────┘
```

| Path | Role | Rule of thumb |
|---|---|---|
| `app.py` | **Web layer.** All 155 routes, auth decorators, quota gate, CSRF, session, PDF proxy. | Routes + HTTP concerns only. No SQL here. |
| `methods/` | **Service layer.** Business logic and third-party integrations. | Reusable operations. No `request`/`session`. |
| `data/` | **Model layer.** One module per table group, thin wrappers over Supabase. | Returns `{"success": bool, ...}` dicts. |
| `cache_manager.py` | **Caching.** L1 in-process, L2 shared, L3 HTTP headers. | `cache.get_cached(key, level, ttl, fetcher)`. |
| `templates/` | **Views.** 58 Jinja2 templates. | `p_*.html` = page, `_*.html` = partial. |
| `static/` | **Assets.** CSS/JS/images + self-hosted PDF.js. | Never CDN the viewer. |
| `dev/` | **Developer tooling.** Not shipped behaviour. | Safe to run; never imported by `app.py`. |
| `docs/` | **Documentation**, organised by purpose — `architecture/` (how it's built), `guides/` (how to do X), `reference/` (lookups), `product/` (intent), `history/` (snapshots, never edited). Index: [`docs/README.md`](../README.md). | |
| `migrations/` | **SQL migrations.** | Applied via Supabase SQL editor. |

---

## 3. `app.py` route clusters

`app.py` is one file, but routes are grouped. Approximate bands:

| Lines | Cluster | Examples |
|---|---|---|
| 500–999 | Bootstrap, auth, quota, static | `/auth`, `/login`, `/api/quota` |
| 1000–1499 | Taxonomy APIs (college/branch/subject) | `/api/colleges`, `/api/departments` |
| 1500–1999 | Social + view logging | `/api/interactions/like`, `/api/document-view` |
| 2000–2499 | Upload & preview | `/upload`, `/preview`, `/local-viewer` |
| 2500–2999 | Account, profile, SEO landings | `/account`, `/pyq`, `/college/<slug>` |
| 3000–3499 | Document delivery | `/pdf-proxy/<name>`, `/api/view-doc/<id>` |
| 3500–3999 | Dashboard & PWA | `/dashboard`, `/sw.js`, `/manifest.json` |
| 4000–4499 | Admin | `/admin/analytics`, `/api/admin/*` |
| 4500–4999 | Store Room (labelling queue) | `/store-room/api/*` |
| 5000–5499 | Memory Wall | `/memorywall`, `/m/<slug>` |
| 5500–5999 | Peer chat (SocketIO) | `/chat`, `/api/chat/online` |

Find any route fast:

```bash
grep -n "@app.route" app.py                    # list all
grep -n "@app.route('/upload'" app.py          # find one
python dev/route_parity.py verify              # confirm none lost
```

---

## 4. `methods/` — service layer

| File | Role |
|---|---|
| `supabase_helper.py` (2.3k L) | **Main data-access hub.** Documents, profiles, ranks, referrals, notifications, audit. Largest service file. |
| `cloudinary_upload.py` | Upload + compress to Cloudinary. **Canonical storage path.** |
| `cloudinary_helper.py` | Cloudinary URL/transform helpers. |
| `storage.py`, `storage_providers.py` | Storage abstraction (Cloudinary / Firebase). |
| `analytics_tracker.py` | GA4-style event capture; registers its own routes. |
| `analytics_reporter.py` / `_routes.py` | Reporting queries + their routes. |
| `analytics_analyzer.py` | Aggregation helpers. |
| `search_api.py` | Search API v2 endpoints (`/api/v2/search`). |
| `indexer.py` | Search index build. |
| `seo_helper.py` | Slug/canonical helpers. |
| `know_me.py`, `know_me_generator.py` | Memory Wall feature. |
| `upload_notifier.py` | Post-upload push notification job. |
| `get_user_uploaded_files.py` | Per-user upload listing. |

---

## 5. `data/` — model layer

| File | Tables |
|---|---|
| `db.py` | Supabase client singleton (schema `abhihub`). |
| `documents.py` | `documents` |
| `profiles.py` | `profiles`, `user_sessions` |
| `interactions.py` | `document_views`, likes, bookmarks, comments |
| `colleges.py` | `colleges`, `departments`, `subjects` |
| `notifications.py` | `notifications` |
| `analytics.py` | analytics tables |
| `raw/` | Local JSON snapshots. **gitignored**, not a source of truth. |

---

## 6. Cross-cutting rules

**Anti-piracy (non-negotiable)**
- Preview in-page only. No download links, no `Content-Disposition: attachment`.
- `/pdf-proxy/` and `/api/view-doc/` set `Content-Disposition: inline`,
  `X-Download-Options: noopen`, `no-store`, and a Referer check.
- **PDF.js is the canonical viewer**, self-hosted at
  `static/pdfjs-6.1.200-dist/`. Never swap the viewer library.

**Auth**
- `@auth_required` — session must exist. API paths get 401 JSON; pages redirect to `/login`.
- `@admin_required` — email must be in `ADMIN_EMAILS` (env, empty by default).
- CSRF on by default, 1h TTL; skipped for `/api/`, `/auth`, `/store-room/api/`.

**Quota / credits**
- Each upload grants `QUOTA_PER_UPLOAD` (19) paper opens; monthly reset.
- `_consume_credit()` gates every paper open. Admins bypass.
- `_check_and_log_view()` is the shared "check quota + log the view" helper —
  use it, don't re-implement.

**Config**
- Everything through env vars. `.env.example` documents them with placeholders.
- Required: `SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`.
- Never commit real credentials. See `SECURITY.md`.

**Logging**
- Use `logging.*`. `print()` is not allowed in `app.py`, `methods/`, `data/`.

---

## 7. `dev/` — tooling

| Path | Role |
|---|---|
| `dev/route_parity.py` | **Refactor safety net.** Snapshots/verifies all URL rules by static AST parse. Run `verify` before every deploy that touched routing. |
| `dev/route_snapshot.json` | Baseline: 150 rules. |
| `dev/check_doc_links.py` | Validates every relative markdown link in `README`/`docs/`. Run after moving or renaming any doc. |
| `dev/bots/` | Internal LLM "company" bots + their reports. |
| `dev/scripts/` | Ops scripts (campaign export/report, exam-pack drip). |

Hidden tooling dirs, left at root deliberately (dot-prefixed, already out
of the way): `.ai/` governance engine + agents, `.agents/` agent specs,
`.record/` task/chat logs, `.codegraph/`, `.documentation/`, `.know_me/`.

---

## 8. Common tasks

| Task | Where |
|---|---|
| Add a route | `app.py`, near its cluster (§3). Then `python dev/route_parity.py snapshot`. |
| Change how a document is stored | `methods/cloudinary_upload.py` |
| Change a DB query | `methods/supabase_helper.py` or the matching `data/*.py` |
| Change the PDF viewer UI | `templates/resource.html` + `static/pdfjs-6.1.200-dist/` |
| Add a cached read | `cache.get_cached(...)` in `cache_manager.py` |
| Add an env var | `.env.example` + read via `os.getenv` |

## 9. Verify before deploy

```bash
python -c "import ast; ast.parse(open('app.py').read())"   # syntax
python dev/route_parity.py verify                          # no route lost
grep -rn "print(" app.py methods/ data/ --include="*.py"   # expect none
git push heroku <branch>:main
```

Related: [`SECURITY.md`](../../SECURITY.md),
[`ROUTES.md`](../reference/ROUTES.md),
[`BUGS.md`](../reference/BUGS.md),
[`REORG_PROGRESS.md`](../history/REORG_PROGRESS.md),
[`CONTRIBUTING.md`](../../CONTRIBUTING.md).
