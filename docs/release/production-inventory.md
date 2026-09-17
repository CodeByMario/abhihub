# AbhiHub Production Inventory & File Classification

## Overview
This document contains the comprehensive inventory and classification of all files and directories in the AbhiHub workspace as of September 11, 2026. This classification serves as the baseline for constructing the allowlisted production runtime package and `.dockerignore` / `.gitignore` production rules.

---

## 1. System & Runtime Detection
- **Backend Framework**: Flask 2.0.1 + Gevent WebSocket (`GeventWebSocketWorker`) + Flask-SocketIO
- **Runtime Environment**: Python 3.12 (standardized via `.python-version`)
- **Frontend Assets**: Tailwind CSS 3.4.1 (compiled via npm script to `static/css/tailwind.min.css`), Vanilla JS, PDF.js 6.1.200 distribution
- **Database & Storage**: Supabase (PostgreSQL `abhihub` schema), Cloudinary (primary doc/image storage), Firebase Admin SDK (legacy fallback storage)
- **Deployment Platform**: Heroku / Container (via `Procfile`: `web: gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 app:app`)
- **Health Endpoints**: `/health`, `/api/health` returning JSON `{ "status": "healthy", "service": "abhihub", "version": "1.0.0", "timestamp": "..." }`

---

## 2. Complete File & Directory Classification

### A. Runtime-Required (Must be present in production execution)
| Path | Description | Role |
| :--- | :--- | :--- |
| `app.py` | Core Flask application, routing, socket handlers, APIs | Application entrypoint |
| `gunicorn.conf.py` | Gunicorn config with Python 3.10+ `collections.abc` gevent compatibility patch | WSGI server boot |
| `cache_manager.py` | Multilevel caching manager | In-memory / data caching |
| `push_api.py` | Web push subscription & notification management API | Push notification backend |
| `push_notifications.py`| Push notification sender & webpush payload dispatcher | Notification worker |
| `scheduled_tasks.py` | Background scheduler (APScheduler) for maintenance & notifications | Periodic background tasks |
| `firebase_config.py` | Firebase environment variable parser (stateless fallback) | Legacy storage config |
| `data/__init__.py` | Data package init | Module system |
| `data/analytics.py` | Analytics models and data aggregators | Analytics logic |
| `data/colleges.py` | College directory data helper | Educational resource index |
| `data/contact_messages.json` | Contact messages store fallback | User messages |
| `data/db.py` | Supabase database access layer | DB operations |
| `data/documents.py` | Document models & query helpers | Document management |
| `data/interactions.py` | Interaction models (views, downloads) | Analytics & gamification |
| `data/notifications.py` | In-app notification queue & schema | User notifications |
| `data/profiles.py` | User profile, session, and quota models | Authentication & state |
| `methods/__init__.py` | Methods package init | Module system |
| `methods/admin_db_helper.py` | Administrative queries & DB operations | Admin tooling |
| `methods/analytics_analyzer.py` | Aggregate analytics calculation engine | Analytics analytics |
| `methods/analytics_reporter.py` | Reporting engine for platform analytics | Admin reports |
| `methods/analytics_reporter_routes.py` | Admin analytics dashboard routes | Analytics web routes |
| `methods/analytics_tracker.py` | User event tracking & ingestion endpoints | Real-time tracking |
| `methods/cloudinary_helper.py` | Cloudinary asset management helpers | Media handling |
| `methods/cloudinary_upload.py` | Image/PDF compression & Cloudinary uploader | Upload processing |
| `methods/encrypted_chat.py` | End-to-end encrypted messaging helpers | Peer chat |
| `methods/get_user_uploaded_files.py` | User file query helpers | Upload history |
| `methods/indexer.py` | Search indexer & Bing IndexNow dispatcher | Search & SEO |
| `methods/know_me.py` | Know Me interactive wall backend | Know Me feature |
| `methods/know_me_generator.py` | Wordcloud & signature image generator | Visual generation |
| `methods/scoring_engine.py` | User engagement, quota & ad gating engine | Gamification / quotas |
| `methods/search_api.py` | Search v2 endpoint & autocomplete logic | Platform search |
| `methods/seo_helper.py` | Dynamic meta tag & sitemap generator | SEO engine |
| `methods/storage.py` | Unified storage interface (Supabase/Cloudinary/Firebase) | File storage |
| `methods/storage_providers.py` | Cloudinary and Supabase storage providers | Storage drivers |
| `methods/supabase_helper.py` | Supabase client & table helper functions | Primary database client |
| `methods/upload_notifier.py` | Notification trigger upon file uploads | Upload alerts |
| `templates/` (all html) | Jinja2 server-rendered templates | UI views & layout |
| `static/` (all css/js/img)| Static CSS, JavaScript, PDF.js, images, fonts | Client-side runtime assets |

---

### B. Build-Required (Needed to compile or prepare assets, excluded from final runtime image)
| Path | Description | Role |
| :--- | :--- | :--- |
| `package.json` | Node package configuration for Tailwind CSS compiler | Frontend build tool |
| `package-lock.json` | Node dependency lockfile | Deterministic node build |
| `tailwind.config.js` | Tailwind CSS configuration & content paths | CSS minification & build |
| `requirements.txt` | Production Python dependencies | Pip installation |
| `.python-version` | Standard Python runtime declaration (3.12) | Tooling / PaaS runtime selector |

---

### C. Deployment-Required (Platform orchestration & process configuration)
| Path | Description | Role |
| :--- | :--- | :--- |
| `Procfile` | Heroku / PaaS worker and web process declaration | Process manager |
| `robots.txt` | Root crawlers instruction file | Search engine indexing |
| `ads.txt` | Google AdSense publisher verification file | Ad network compliance |
| `favicon.ico` | Root favicon fallback | Browser tab icon |

---

### D. Migration-Required (Run via CI/CD or admin migration pipeline, not in static container web root)
| Path | Description | Role |
| :--- | :--- | :--- |
| `migrations/` | SQL schema migrations (008 to 027) | Database schema evolution |
| `apply_migration_017.py` | Helper script for Supabase RPC migration | One-off migration helper |

---

### E. Service Worker & PWA Files (Client-side offline & push workers)
| Path | Description | Role |
| :--- | :--- | :--- |
| `static/sw.js` | Service Worker handling caching, offline fallback, and push notifications | PWA Service Worker |
| `static/manifest.json` | PWA web app manifest | PWA metadata & icons |
| `templates/offline.html` | Offline fallback template rendered by service worker | Offline UX |

---

### F. Notification Files
| Path | Description | Role |
| :--- | :--- | :--- |
| `push_api.py` | Blueprint exposing `/api/push/*` and `/api/notifications/*` | Notification endpoints |
| `push_notifications.py`| Webpush payload generation & VAPID signing | Push delivery |
| `static/js/push-notifications.js` | Frontend push subscription registration & permissions | Browser subscription |
| `static/js/notification-bell.js` | Notification bell UI, unread badge & dropdown | In-app notification UI |
| `templates/notifications.html` | User notification center | User notification page |
| `templates/admin_notification_panel.html`| Admin broadcast & push dispatch UI | Admin push dashboard |

---

### G. Analytics Files
| Path | Description | Role |
| :--- | :--- | :--- |
| `methods/analytics_tracker.py` | Server-side event tracker & session recorder | Analytics backend |
| `methods/analytics_analyzer.py` | Statistical aggregation engine | Metrics computation |
| `methods/analytics_reporter.py` | Admin analytics report generator | Performance analytics |
| `methods/analytics_reporter_routes.py` | Routes for analytics reporting UI | Reporting endpoints |
| `static/js/analytics.js` | Core client analytics event emitter | Client-side tracking |
| `static/js/analytics-helper.js` | Helper for page views & interaction instrumentation | Event helpers |
| `templates/google_tag.html` | Google Analytics (GA4) / Google Tag manager include | Tag injection |
| `templates/admin_analytics.html`| Admin analytics dashboard view | Metrics dashboard |

---

### H. Public Assets
| Path | Description | Role |
| :--- | :--- | :--- |
| `static/css/` | Compiled & raw stylesheets (`tailwind.min.css`, `style.css`, etc.) | Styling |
| `static/js/` | Frontend scripts (auth, UI, modals, chat) | Client logic |
| `static/images/` | Static illustrations, logos, SVG badges | UI visual assets |
| `static/premium/` | Premium cards, themes, and icons | Premium feature assets |
| `static/pdfjs-6.1.200-dist/` | Prebuilt PDF.js library and viewer workers | In-browser PDF rendering |

---

### I. Secret & Local-Only Files (STRICT EXCLUSION from any public release or runtime artifact)
| Path | Reason for Exclusion |
| :--- | :--- |
| `.env` | Contains live production secrets, database credentials, API keys |
| `data/cache/cloudinary_files_cache.json` | Local dev/temporary cached JSON |
| `data/raw/*.json` | Local mock files (`admin_users.json`, `data.json`, `suspects.json`, etc.) |
| `firebase-auth.json` (if present) | Service account private key |

---

### J. Test-Only Files (EXCLUDE from production runtime)
| Path | Reason for Exclusion |
| :--- | :--- |
| `tests/` | Unit, integration, readiness, and security test files |
| `.pytest_cache/` | Pytest execution cache |
| `automation_test_report.md` | Test execution logs and reports |

---

### K. Documentation & Agent Instructions (EXCLUDE from production runtime)
| Path | Reason for Exclusion |
| :--- | :--- |
| `*.md` (`README.md`, `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md`, etc.) | Developer and repo documentation |
| `docs/` | Architectural specs, guides, audit logs |
| `conductor/` | Conductor task registry, plans, and specs |
| `antigravity-instruction.md` | Agent instruction file |
| `notification-*-instruction.md` | Agent instruction files |
| `production-*-instruction.md` | Agent instruction files |
| `work complete.md`, `working on.md` | Developer scratchpads |
| `STATUS_FIX_SUMMARY.md`, `pdf_viewer_audit.md` | Temporary audit reports |

---

### L. Development-Only & Stray / Unknown Files (EXCLUDE from production runtime)
| Path | Reason for Exclusion | Action |
| :--- | :--- | :--- |
| `bot.py` | GitHub repo management bot (PR merge, triage) | Dev automation only |
| `setup.py` | GitHub automation setup script (labels/templates) | Dev automation only |
| `config/labels.json`, `config/contributors.json` | GitHub bot configuration | Dev automation only |
| `scripts/auto_assign.py`, `scripts/feature_planner.py`| GitHub bot helper scripts | Dev automation only |
| `sync_firebase_documents.py` | One-off migration sync script | Admin utility only |
| `dev/` | Route parity scripts, bug verification tools | Dev utility only |
| `trash/` | Stray old static assets and discarded scripts | Stray trash |
| `icons/` | Raw unpackaged icons (duplicate of `static/premium/icons`) | Raw asset folder |
| `getSettings.ts` | Orphan stray TypeScript file from tom-select | Stray source |
| `E?UsersabhihubNew` | Accidental empty file created by corrupted path string | Stray corrupted file |
| `software-development/` | Local audit notes | Dev documentation |
| `skills/` | Agent skill definitions | Agent customizations |
| `.agent/`, `.agents/`, `.ai/`, `.codegraph/`, `.know_me/`, `.record/`, `.wip/`, `.documentation/`, `.vscode/` | IDE & agent workspaces | Tooling metadata |
| `.venv/`, `node_modules/`, `__pycache__/` | Local environments and bytecode | Local build artifacts |
