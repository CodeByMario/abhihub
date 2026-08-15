# Project Rules — AbhiHub Specific

**Status:** Effective Immediately
**Source:** .ai/rules/project.md

---

## Technology Stack

| Component       | Standard                    |
|-----------------|-----------------------------|
| Language        | Python 3.11+                |
| Web Framework   | Flask 2.0.1                 |
| Database        | Supabase (PostgreSQL)       |
| Frontend        | Tailwind CSS 3.4 + vanilla  |
| Auth            | Supabase Auth               |
| File Storage    | Cloudinary                  |
| Push            | Firebase Cloud Messaging    |
| Hosting         | Heroku                      |
| Build Tool      | Python pip + npm            |
| Tests           | pytest                      |

## Required Standards

- Use Python 3.11+ (specified in `.python-version`).
- Use Flask routing with `render_template` for HTML pages.
- Use Supabase client for all database operations.
- Use Cloudinary SDK for file uploads.
- Use `methods/` directory for utility modules.
- Use `migrations/` for SQL schema changes.
- Use `docs/` and `.documentation/` for documentation.
- Use `.record/tasks/<AGENT-ID>/` for task logs (EP-001).

## File Organization

```
project/
├── app.py                    # Flask app entry point
├── requirements.txt          # Python dependencies
├── package.json              # Node/npm dependencies
├── .python-version           # Python version pin
├── Procfile                  # Heroku deployment
├── .env                      # Environment variables (NEVER COMMIT)
├── src/                      # Source modules
│   ├── methods/              # Utility functions
│   ├── data/                 # Static data (colleges, departments)
│   └── routes/               # Route blueprints (if any)
├── templates/                # Jinja2 HTML templates
├── static/                   # CSS, JS, images
│   ├── css/
│   ├── js/
│   └── uploads/
├── tests/                    # Test suite
├── migrations/               # SQL migration files
├── docs/                     # User-facing docs
├── .documentation/           # Technical docs
├── .ai/                      # AI governance control plane
│   ├── agents/               # Agent manifests
│   ├── rules/                # Policy rules
│   ├── history/              # Change ledger + reports
│   ├── state/                # Project state
│   └── manifests/            # Generated manifests
├── .record/                  # EP-001 company records
└── .codegraph/               # Code dependency graph
```

## Code Quality Requirements

- All new routes must be documented in `ROUTES.md`.
- All new public APIs must be documented in `.documentation/5_apis.md`.
- Architecture decisions must be recorded in `.documentation/`.
- All agent work must be recorded in `.record/tasks/<AGENT-ID>/`.
- Tests must pass before any PR is merged.
- Follow the existing CSS pipeline (see README.md for pipeline structure).

read: app.py, src/**, tests/**, templates/**, static/**, docs/**, .documentation/**, .ai/rules/**, .ai/agents/**, .record/**, requirements.txt, package.json, ROUTES.md, README.md, CHANGELOG.md, migrations/**, .env.example

write: src/**, tests/**, templates/**, static/css/**, static/js/**, docs/**, .documentation/**, migrations/**, ROUTES.md, CHANGELOG.md, .record/tasks/**
