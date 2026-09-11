# AbhiHub Production Readiness Agent Instructions

## Objective

Make the AbhiHub project production-ready without breaking existing behavior, then place every change on a new Git branch and prepare a pull request. Do not merge, deploy, push, or delete anything without explicit confirmation from the repository owner.

The application includes Google and email authentication, dashboard, uploads, profile, storeroom, PYQs, notes, and analytics. Treat analytics correctness, privacy, security, reliability, and rollback as production requirements.

## Non-negotiable rules

- Use Ponytail coding rules.
- Use the Conductor workflow: inspect, plan, implement, test, review, document.
- Work only in a new branch created from the current base branch.
- Never work directly on `main`, `master`, `production`, or another protected branch.
- Before changing files, record the current branch, commit, status, runtime versions, and test commands.
- Do not reset, rebase, force-push, delete branches, or discard user changes.
- Do not commit secrets, credentials, private keys, tokens, `.env` files, service-account JSON files, database dumps, or real user data.
- Do not expose authentication tokens, emails, note contents, passwords, or sensitive free text in logs or analytics.
- Preserve existing features unless a change is required for security or correctness.
- Do not upgrade major dependencies without showing compatibility risks and obtaining approval.
- Do not push to the remote or create/merge a pull request until the user explicitly confirms after reviewing the final report.

## Phase 0: repository safety

1. Inspect Git status and determine the base branch.
2. If there are uncommitted changes, do not overwrite them. Report them and ask whether to include, stash, or leave them untouched.
3. Inspect remotes without exposing credentials.
4. Create a branch with a descriptive name, for example:

```text
chore/production-readiness
```

If the name already exists, use a safe unique name such as `chore/production-readiness-2`.
5. Record the branch name and starting commit in `docs/production-readiness/baseline.md`.

## Phase 1: full audit

Inspect the entire repository before implementation. Identify:

- frontend framework and build system;
- backend framework and API routes;
- database, migrations, indexes, and backup strategy;
- authentication and authorization;
- file upload and storage configuration;
- analytics SDK/tag and event implementation;
- environment variables and configuration loading;
- deployment platform and CI/CD;
- tests, linting, formatting, type checking, and existing health checks;
- error handling, logging, monitoring, and rate limiting;
- dependency versions and known vulnerabilities;
- admin and moderation functionality;
- public routes, private routes, and access-control boundaries.

Create `docs/production-readiness/audit.md` with findings, severity, evidence, affected files, and recommended action. Use `critical`, `high`, `medium`, and `low` severity.

Do not claim production readiness based only on a successful build.

## Phase 2: production checklist

Create `docs/production-readiness/checklist.md` and verify each item.

### Build and code quality

- Production build succeeds from a clean install.
- Type checking succeeds where supported.
- Linting and formatting checks succeed.
- Tests pass, including authentication, access control, upload, content view, save, profile, storeroom, and analytics flows.
- No debug statements, mock endpoints, demo accounts, placeholder secrets, test routes, or development-only bypasses remain.
- Error responses do not reveal stack traces, SQL, filesystem paths, tokens, or internal configuration.
- All migrations are reviewed and safe to run in production.
- Lockfiles are present and dependency versions are reproducible.
- Dependency and secret scans are run and documented.

### Authentication and authorization

- Google login and email login work in production configuration.
- Redirect URIs and allowed origins are production-specific.
- Passwords are handled only by a trusted authentication provider or a secure, reviewed implementation.
- Sessions and cookies use secure settings appropriate for production: HTTPS, `HttpOnly`, `Secure`, and suitable `SameSite` behavior.
- Logout invalidates or clears sessions correctly.
- Protected routes enforce authorization on the server, not only in the UI.
- A user cannot read, modify, delete, or publish another user's private data by changing an ID.
- Admin, moderation, upload, profile, and storage permissions are explicitly checked.
- Login, signup, password reset, upload, and sensitive APIs have abuse protection and rate limits.
- No credentials or provider secrets are stored in the client bundle.

### Upload and content safety

- Validate file type by content and allowlist, not only filename extension.
- Enforce file-size, filename, quantity, and request limits.
- Sanitize filenames and prevent path traversal.
- Store uploads outside executable web roots or in a safe object-storage bucket.
- Prevent uploaded files from executing as code.
- Scan, moderate, or quarantine content according to the project policy.
- Ensure private content cannot be accessed through predictable URLs.
- Verify ownership before update, delete, publish, download, or moderation actions.
- Handle interrupted, duplicate, and failed uploads safely.
- Do not send full note content or file contents to analytics.

### API and web security

- Validate and normalize all user input.
- Use parameterized database queries or a safe ORM.
- Configure CORS with an explicit production allowlist.
- Add suitable security headers, including a carefully tested Content Security Policy, HSTS when HTTPS is fully ready, clickjacking protection, MIME sniffing protection, and an appropriate referrer policy.
- Disable directory listings and unnecessary HTTP methods.
- Ensure `.git`, source maps where inappropriate, backups, environment files, debug endpoints, and internal documentation are not publicly accessible.
- Protect against CSRF where cookie-based authentication is used.
- Use safe redirects and prevent open redirects.
- Add request size, timeout, and pagination limits.
- Avoid leaking whether sensitive accounts or records exist where that matters.

### Reliability and operations

- Add a health endpoint that checks application readiness without leaking secrets.
- Add structured logs with request IDs and redaction.
- Do not log passwords, tokens, authorization headers, cookies, emails, private note text, or raw request bodies.
- Add error monitoring with environment and release tags.
- Add performance monitoring for API latency, page load, upload duration, and failure rate.
- Configure database backups, retention, restore testing, and migration rollback procedures.
- Configure storage backup or recovery where applicable.
- Add graceful handling for database, storage, analytics, and third-party-provider failures.
- Define alert thresholds and an incident response contact/process.
- Document deployment, rollback, recovery, and emergency-disable procedures.

### Analytics production validation

- Keep analytics behind consent and environment controls where required.
- Separate development, staging, internal, and production traffic.
- Prevent duplicate page views and duplicate business events.
- Confirm Google and email login methods are distinguishable without sending personal data.
- Confirm reader, uploader, and contributor-reader classifications use reliable events.
- Confirm successful uploads are server-confirmed.
- Confirm analytics failures do not break core application features.
- Validate events using the analytics debug facility or validation endpoint before production.
- Document all event names, required parameters, custom definitions, audiences, and known limitations.

## Phase 3: implementation strategy

After the audit, create a Conductor plan with:

1. critical security and data-loss issues;
2. authentication and authorization fixes;
3. upload and content-safety fixes;
4. reliability and observability;
5. analytics validation;
6. test coverage;
7. deployment and rollback documentation.

Implement in small, reviewable commits. Prefer focused commits such as:

```text
fix(auth): harden production session configuration
fix(uploads): validate files and enforce ownership
feat(observability): add redacted request logging and health check
test(production): add critical user-flow coverage
docs(deploy): document release and rollback procedure
```

Do not make unrelated refactors.

## Phase 4: tests and verification

Run the repository's existing commands first. Then run appropriate equivalents for the detected stack:

- clean dependency installation;
- lint;
- formatting check;
- type check;
- unit tests;
- integration tests;
- end-to-end tests;
- production build;
- migration validation;
- dependency vulnerability scan;
- secret scan;
- container or artifact scan if applicable.

Create tests for:

- Google login and email login;
- logout and session expiry;
- unauthorized access;
- cross-user record access;
- upload validation and ownership;
- upload failure and retry;
- notes and PYQs view/save/download flows;
- profile and storeroom permissions;
- analytics event privacy and deduplication;
- error responses and rate limits;
- health check and graceful dependency failure.

Never use real production credentials or real user data in tests.

## Phase 5: final review

Create `docs/production-readiness/final-report.md` containing:

- branch name and starting commit;
- changed files;
- commit list;
- completed checklist items;
- unresolved risks and their severity;
- test commands and results;
- security scan results;
- database migration details;
- environment variables required, with names only and no values;
- manual steps required in Google/Firebase, hosting, storage, database, analytics, OAuth, and DNS consoles;
- deployment steps;
- rollback steps;
- monitoring and alerting steps;
- explicit statement of whether the branch is ready for review or still needs work.

Create `docs/production-readiness/deployment-runbook.md` with:

1. pre-deployment backup;
2. environment verification;
3. migration order;
4. deployment command or platform procedure;
5. smoke tests;
6. analytics validation;
7. monitoring window;
8. rollback procedure;
9. post-deployment verification.

## Completion gate

At the end, stop before push and pull-request creation. Show the user:

- current branch;
- current Git status;
- commit history created by the agent;
- test results;
- unresolved critical/high findings;
- exact files changed;
- whether any user changes were left untouched;
- the exact proposed push and pull-request action.

Ask for explicit confirmation before:

- pushing the branch to the remote;
- creating a pull request;
- merging or deploying.

A successful production build is not permission to push or deploy.
