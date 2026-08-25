# Flashcard — AbhiHub

## Project Purpose
Student-driven academic resource hub for engineering students to share and access study materials.

## Architecture Overview
Flask monolith with 155 routes, Supabase (Postgres + RLS), Cloudinary file storage, PDF.js in-browser viewer only.

## Technology Stack
- Web framework: Flask (gunicorn + geventwebsocket)
- Database/auth: Supabase (Postgres, schema `abhihub`)
- File storage: Cloudinary (Firebase Storage as legacy fallback)
- PDF viewer: PDF.js, self-hosted
- Realtime: Flask-SocketIO
- Styling: Tailwind + custom CSS pipeline
- Hosting: Heroku

## Important Paths
- `app.py` — Flask entry point (5.7k lines, 155 routes)
- `methods/` — Service layer
- `data/` — Model layer
- `templates/` — Jinja2 templates
- `static/` — CSS/JS/images + self-hosted PDF.js
- `docs/` — Documentation

## Critical Constraints
- Never create directory named `app/` at repo root
- PDF.js is canonical viewer, never swap to Adobe Embed SDK as primary
- In-page PDF preview only — no download links
- `@auth_required` on all API routes, `@admin_required` for admin actions
- No `print()` in production code (`app.py`, `methods/`, `data/`)
- Use `logging.*` instead

## Frequently Used Commands
- `python dev/route_parity.py verify` — confirm no route was lost after routing changes
- `grep -rn "print(" app.py methods/ data/ --include="*.py"  # check for print() calls`
- `python3 -c "from app import app"` — verify imports work
- `git push heroku <branch>:main` — deploy to Heroku

## Key Decisions
- Supabase anon key is publishable by design; RLS is the security boundary
- CSS pipeline consolidated into `static/css/pipeline/` with 11 modular files
- Route documentation in `ROUTES.md` — 148 REST routes + 6 Socket.IO events
- PDF proxy `/pdf-proxy/` requires auth after security fixes
- Admin emails from `ADMIN_EMAILS` env var, not hardcoded