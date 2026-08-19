# AbhiHub

A study-material platform for engineering students. Upload and browse
previous-year question papers, notes, and practicals — organised by
college, branch, semester, and subject.

Documents are **previewed in-browser only** (PDF.js), never downloaded.

- **Live:** https://abhihub.edu.eu.org
- **App:** https://app.abhihub.run.place

---

## Stack

| Layer | Technology |
|---|---|
| Web framework | Flask (gunicorn + gevent) |
| Database / auth | Supabase (Postgres, schema `abhihub`) |
| File storage | Cloudinary (Firebase Storage as legacy fallback) |
| PDF viewer | PDF.js, self-hosted |
| Realtime | Flask-SocketIO |
| Styling | Tailwind + a custom CSS pipeline |
| Hosting | Heroku |

---

## Quick start

```bash
git clone <repo-url>
cd abhihub

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then fill in real values
python app.py                      # http://127.0.0.1:5000
```

Minimum required env vars — see [`.env.example`](.env.example) for the full list:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session signing |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon key |

> Never commit `.env`. See [SECURITY.md](SECURITY.md).

---

## Project layout

```
app.py                  Flask entry point — all HTTP routes
cache_manager.py        L1/L2/L3 caching
push_api.py             Web-push endpoints
push_notifications.py   Push delivery
scheduled_tasks.py      Background jobs
methods/                Service layer (Supabase, Cloudinary, analytics, search)
data/                   Model layer — one module per table group
templates/              Jinja2 templates (p_* = page, _* = partial)
static/                 CSS / JS / images + self-hosted PDF.js
tests/                  pytest suite
dev/                    Developer tooling (not shipped)
docs/                   Documentation
migrations/             SQL migrations
```

> **Do not create a directory named `app/`.** It would shadow `app.py`
> and silently break routing. See
> [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md).

---

## Documentation

**Architecture**
- [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) — layer map, what plays what role
- [CSS_PIPELINE.md](docs/architecture/CSS_PIPELINE.md) — stylesheet structure

**Guides**
- [USER_GUIDE.md](docs/guides/USER_GUIDE.md) — end-user walkthrough
- [GA4_IMPLEMENTATION.md](docs/guides/GA4_IMPLEMENTATION.md) — analytics setup
- [FILE_HISTORY_SETUP.md](docs/guides/FILE_HISTORY_SETUP.md) — access-history feature
- [COMPANY_SKILLS_AND_BOTS.md](docs/guides/COMPANY_SKILLS_AND_BOTS.md) — internal bots

**Reference**
- [ROUTES.md](docs/reference/ROUTES.md) — full route map
- [BUGS.md](docs/reference/BUGS.md) — known issues + fix plan

**Product**
- [IDEA.md](docs/product/IDEA.md) — vision and scope

**History** — [docs/history/](docs/history/) holds point-in-time records
(audits, migration logs). Useful for context, not current truth.

---

## Development

```bash
pytest                                  # run tests
python dev/route_parity.py verify       # confirm no route was lost
npm run build:css                       # rebuild Tailwind
git push heroku <branch>:main           # deploy
```

Run `dev/route_parity.py verify` after **any** change to routing — it
fails loudly if a URL rule disappears.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: keep secrets in env
vars, use `logging` (not `print`), don't add download paths for
documents, and don't swap the PDF viewer.

## License

MIT — see [LICENSE](LICENSE).
