Contributing & Lightweight Dev Run
================================

This repository supports a lightweight developer runtime for fast local
iteration. Use the minimal requirements file when you don't need heavy
external services.

Setup (Unix / macOS):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-min.txt
```

Setup (Windows PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-min.txt
```

Run the dev server (Unix / macOS):

```bash
export FLASK_APP=app.py
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=5000
```

Run the dev server (Windows PowerShell):

```powershell
$env:FLASK_APP = 'app.py'
$env:FLASK_ENV = 'development'
flask run --host=0.0.0.0 --port=5000
```

Notes:
- This minimal runtime intentionally excludes optional/production
  dependencies such as `firebase-admin`, `supabase`, `cloudinary`, and
  push/notifications libraries. Add those from `requirements.txt` if you
  need full functionality.
- Use environment variables (see `.env`) for credentials; do NOT commit
  `firebase-auth.json` to the repository.

Recording your work:
- After any change, append a short entry to the relevant `.record/tasks/<ASSIGNEE>/` file
  and add a line to the daily log file `.record/tasks/<ASSIGNEE>/daily/YYYY-MM-DD.md`.

Frontend CSS build (optional)
-----------------------------

This project uses Tailwind for utility classes. To build the site CSS you will
need Node.js and the dev dependency `tailwindcss` (already listed in `package.json`).

Install dev dependencies:

```bash
npm install
```

Build CSS once:

```bash
npm run build:css
```

Watch CSS (development):

```bash
npm run watch:css
```

Output file: `static/css/tailwind.min.css` — include this in your templates instead
of the fragmented pipeline files for better caching and performance.
