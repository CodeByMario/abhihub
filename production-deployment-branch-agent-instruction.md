# AbhiHub Production Deployment Branch Agent Instructions

## Objective

Create a separate production-deployment branch and deployment artifact for AbhiHub containing only files required to build, deploy, configure, and run the production application. Keep development source, tests, documentation, agent instructions, local configuration, temporary files, and unrelated assets out of the production artifact.

Do not blindly delete files from the source repository. The repository branch should remain reviewable and recoverable. Prefer a reproducible build/deployment artifact, a production package, or a multi-stage container image. Only remove files from the branch when their runtime/build/deployment role has been proven unnecessary and the user approves the deletion.

Use the required skill stack:

1. **Ponytail** — coding discipline, minimal changes, safety, testing, and review.
2. **Conductor**, preferably `conductor-implement` — inspect, plan, implement, test, review, document.
3. **Antigravity Awesome Skills** — use only relevant skills for repository analysis, build/release packaging, framework deployment, Docker/containerization, security, dependency pruning, testing, and Git workflows.

Before work begins, identify the exact installed skill names and paths. Record which skills were actually used. Do not claim to have used unavailable skills.

## Safety rules

- Never delete the user's current work, branches, commits, or files without explicit approval.
- Start from the selected base branch and create a new branch such as `release/production-deployment`.
- Check Git status first. Stop if uncommitted changes could be affected.
- Do not commit `.env` files, secrets, private keys, service-account files, tokens, database dumps, or real user data.
- Do not put credentials in a container image, build artifact, repository, logs, or generated manifest.
- Do not include `.git`, `.github` secrets, local IDE settings, agent instructions, markdown documentation, test fixtures, screenshots, source maps, debug output, or development tools in the runtime artifact unless the detected platform explicitly requires a particular file.
- Do not remove required runtime assets, migrations, manifests, service-worker files, public files, license notices, or framework files merely because they look unused.
- Do not disable security checks to make the artifact smaller.
- Do not push, create a pull request, merge, deploy, or delete a remote branch without explicit confirmation.

## Critical distinction

Maintain three clearly documented layers:

1. **Source repository** — may contain source code, tests, docs, CI configuration, migrations, and development tools.
2. **Build context** — files sent to the build process after applying ignore rules.
3. **Production runtime artifact** — files actually shipped to the server, hosting platform, or container.

The goal is to minimize layers 2 and 3 without damaging layer 1. A production branch must not be a destructive copy of the project unless the deployment platform requires that model.

## Phase 1: inspect and inventory

Create `docs/release/production-inventory.md` temporarily during the work. It may remain in the source branch but must not enter the runtime artifact.

Inspect and classify every top-level file and directory as one of:

- required at build time;
- required at runtime;
- required for deployment;
- required for database migrations;
- required for service worker/PWA behavior;
- required for notification delivery;
- required for analytics configuration;
- development-only;
- test-only;
- documentation-only;
- generated and reproducible;
- secret or local-only;
- unknown and requiring review.

Detect:

- frontend framework and build output;
- backend framework and start command;
- package manager and lockfile;
- runtime version;
- server entrypoint;
- static/public assets;
- server-side migrations and seed requirements;
- service worker and manifest;
- notification files and provider configuration;
- analytics code and public identifiers;
- environment variables, showing names only;
- deployment platform, Docker, serverless, or VM configuration;
- health endpoint and required ports;
- database and storage dependencies;
- production build and smoke-test commands.

Do not include secrets in the inventory.

## Phase 2: define the deployment contract

Create `docs/release/deployment-contract.md` with:

- build command;
- install command;
- runtime start command;
- required runtime version;
- required environment variable names and descriptions, never values;
- required port and host behavior;
- health-check path;
- readiness and liveness behavior;
- migration command and migration order;
- static asset directory;
- persistent storage requirements;
- service-worker path and scope;
- notification worker/queue requirements;
- analytics configuration requirements;
- external services;
- rollback method;
- shutdown behavior;
- expected production logs and metrics.

## Phase 3: choose the artifact strategy

Select the strategy matching the detected deployment platform and explain why:

### Container deployment

Prefer a multi-stage Docker build:

- builder stage installs build and development dependencies;
- builder stage compiles, bundles, minifies, and generates production output;
- runtime stage uses a minimal supported runtime base;
- runtime stage copies only explicit production artifacts;
- runtime stage installs only production dependencies;
- runtime image contains no source files, compilers, package caches, tests, docs, Git metadata, or development tools unless required at runtime;
- run as a non-root user where supported;
- configure a health check;
- use a `.dockerignore` that excludes secrets, docs, tests, local files, caches, and unrelated build output;
- pin or constrain base-image versions and document updates.

### Platform build deployment

If the hosting platform builds from the repository, configure its build and ignore settings so tests/docs/dev-only directories do not become runtime files. Do not exclude files needed by the platform's build process.

### Static frontend deployment

Ship only the generated static output, required manifest/icons, service worker, public assets, and hosting configuration. Ensure HTML references the correct hashed CSS and JavaScript assets. Do not ship source maps unless deliberately protected and required for monitoring.

### Server/package deployment

Create a production package containing the compiled server or required runtime source, production dependencies, migrations, public assets, service worker, and explicit configuration templates. Do not copy the entire repository.

## Phase 4: explicit inclusion and exclusion

Create a machine-readable or clearly documented manifest at `release/production-manifest.json` in the source branch. It must list:

- included files/directories;
- excluded files/directories;
- reason for each exclusion;
- generated files;
- required runtime environment variables by name;
- artifact checksum or build identifier.

Use allowlisting for the runtime artifact where practical. Do not rely only on a long exclusion list.

Typical exclusions, subject to verification:

```text
.git/
.github/
.vscode/
.idea/
*.md
!LICENSE
!NOTICE
.env
.env.*
!.env.example
node_modules/
coverage/
.nyc_output/
.pytest_cache/
__pycache__/
*.pyc
test/
tests/
__tests__/
fixtures/
mock-data/
storybook-static/
playwright-report/
cypress/videos/
cypress/screenshots/
scripts/dev/
tmp/
logs/
*.log
*.bak
*.tmp
source maps when not required
agent instructions
local database files
```

Never apply these patterns without checking the detected framework. For example, a service worker, migration directory, `public/` asset, runtime template, license, or framework manifest may be necessary.

## Phase 5: production hardening

Before packaging:

- run a clean install from the lockfile;
- run lint, type checking, tests, and production build;
- remove debug routes, test accounts, mock providers, development bypasses, and test data;
- verify error responses do not expose stack traces or secrets;
- verify authorization for profile, upload, notes, PYQs, storeroom, and notification endpoints;
- verify upload validation and safe storage;
- verify service-worker and notification files remain available;
- verify analytics does not receive personal or secret data;
- scan dependencies and final artifact for secrets;
- scan final artifact for `.git`, `.env`, private keys, tokens, database dumps, test credentials, and unnecessary source files;
- verify no production code depends on a file excluded from the artifact;
- verify the artifact contains no debug/test code that could create a backdoor.

## Phase 6: build and inspect the artifact

Create a reproducible build script such as `scripts/build-production-artifact.*` only if the project convention supports it. The script must:

1. start from a clean workspace or clean build directory;
2. install exact locked dependencies;
3. build frontend and backend outputs;
4. copy only allowlisted runtime files;
5. inject no secrets;
6. write build metadata containing version/commit/build time without sensitive data;
7. produce a checksum or digest;
8. run an artifact inspection;
9. fail if forbidden files or secret patterns are present;
10. run the production smoke test against the artifact.

If Docker is used, build and inspect the final runtime image, not just the builder image.

Verify:

- production server starts;
- health endpoint succeeds;
- authentication works with configured production providers;
- `/profile` update works;
- notes and PYQs load;
- uploads work with safe storage;
- storeroom works;
- notifications can register/send according to the configured channel;
- analytics events still work without exposing private data;
- service worker registers and receives the expected current assets;
- old cache cleanup and asset versioning work;
- database migrations are available through the documented process;
- graceful shutdown works;
- logs are structured and redacted.

## Phase 7: branch and commits

Create the branch only after the baseline is recorded:

```text
release/production-deployment
```

If it exists, choose a safe unique branch name.

Use focused commits, for example:

```text
build(release): define production artifact contract
build(release): add production ignore and packaging rules
build(docker): create minimal multi-stage runtime image
security(release): remove development paths and secret risks
test(release): add artifact inspection and smoke tests
docs(release): add deployment and rollback runbook
```

Do not commit temporary inspection output unless it is intentionally part of source documentation. The final runtime artifact must not include Markdown, agent instructions, audit reports, or test reports unless the hosting platform explicitly requires them.

## Phase 8: final verification

Create a temporary staging artifact and compare it against the manifest. Report:

- total files and size before and after;
- included runtime files;
- excluded files and reasons;
- build identifier and checksum;
- dependency production/dev breakdown;
- scan results;
- smoke-test results;
- required manual platform settings;
- unresolved risks;
- rollback procedure.

The final production artifact must satisfy:

- no `.git` directory;
- no secrets or private keys;
- no `.env` values;
- no test/debug/development code unless required by runtime;
- no unnecessary Markdown or agent instructions;
- no local caches, logs, screenshots, fixtures, or database dumps;
- only required runtime dependencies;
- required migrations, service worker, manifest, public assets, and license notices preserved;
- deterministic build and repeatable deployment;
- health check and smoke test pass.

## Required deliverables

Create or update in the source branch:

- `release/production-manifest.json`;
- `release/build-production-artifact.*` if appropriate;
- `.dockerignore` if Docker is used;
- `Dockerfile` or platform build configuration if required;
- `docs/release/production-inventory.md`;
- `docs/release/deployment-contract.md`;
- `docs/release/deployment-runbook.md`;
- `docs/release/rollback-runbook.md`;
- artifact inspection and smoke tests;
- final production-readiness report.

These documentation files are for maintainers and deployment review. They must remain in the source branch only and must not be copied into the runtime artifact.

## Completion gate

Stop before pushing, opening a pull request, merging, or deploying. Show:

1. branch name and starting commit;
2. current Git status;
3. all commits created;
4. exact production artifact contents;
5. excluded files and reasons;
6. artifact size and checksum;
7. security and secret-scan results;
8. tests and smoke-test results;
9. unresolved issues;
10. exact proposed push command and pull-request summary.

Ask for explicit confirmation before any remote Git or deployment action.
