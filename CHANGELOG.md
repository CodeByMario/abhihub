# Changelog — AbhiHub

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Governance Engine** (`.ai/`) — Multi-agent governance system with Policy Engine,
  Change Ledger, Project State Manager, Agent Gateway, and Governance Engine.
  Supports AUDIT / MAINTAIN / GOVERN / EMERGENCY modes.
- **Agent manifests** — `coding-agent.yaml`, `research-agent.yaml`, `testing-agent.yaml`,
  `documentation-agent.yaml`, `cleanup-agent.yaml` with role-based permissions.
- **CLI** (`governo.py`) — 13 subcommands for audit, onboarding, mode switching,
  request approval, and change log inspection.
- **pytest** added to `requirements.txt` for test infrastructure.

### Changed
|- `.gitignore` — Hardened: added `.env.*`, `cors.json`, `icons.json`, sensitive `data/*.json` files, `trash/`, audit reports.
|- `requirements.txt` — Added `pytest` and `pytest-timeout` as dev dependencies.
|- `ROUTES.md` — Added 27 previously undocumented routes (account, admin, college, academic pages).
|- `.documentation/5_apis.md` — Expanded from 6 to 61 documented API endpoints across 17 categories.

### Fixed
|- `firebase-auth.json` was tracked in git — untracked via `git rm --cached`.
|- Sensitive data files (`admin_users.json`, `push_subscriptions.json`, `suspects.json`) were tracked — untracked.
|- Missing `.env.example` — created with all required environment variables.
|- `agent_gateway.py` — Critical-risk operations now require explicit approval in GOVERN mode (not auto-executed).
|- `project_state.py` — Test runner now uses `sys.executable` for proper venv python invocation.

---

## [0.8.2] — 2025-07-10

### Added
- MemoryWall / Know Me feature — public memory wall pages with word cloud,
  signature composite, and spam protection.
- File Access History tracking with `public.file_access_history` table.
- Promo / Notification System with in-app announcement cards.
- Referral system with unique referral codes.
- PWA support with service worker and offline fallback.

### Changed
- CSS pipeline consolidated into `static/css/pipeline/` with 11 modular files.
- Route documentation auto-generated via `route-dependency-agent`.

---

## [0.8.1] — 2025-06-26

### Added
- Search architecture with pre-built index and client-side web worker.
- Document ranking and leaderboard system.
- Paper quota system for free-tier users.

### Changed
- Firebase configuration modularized into `firebase_config.py`.

---

## [0.8.0] — 2025-05-06

### Added
- Initial AbhiHub platform with user authentication (Supabase Auth).
- Document upload with Cloudinary storage and AES encryption.
- Push notification system with VAPID keys.
- Admin dashboard with user management and document moderation.
- College/department onboarding system.
