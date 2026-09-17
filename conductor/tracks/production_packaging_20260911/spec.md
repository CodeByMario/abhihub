# Track Specification: AbhiHub Production Deployment Packaging & Branch Isolation

## Objective
Establish a hardened, minimal production deployment packaging pipeline and dedicated release branch `release/production-deployment`. Ensure the runtime artifact excludes all development, test, markdown, local configuration, and unneeded assets while retaining all required runtime, build, migration, service worker, notification, and analytics files.

## Scope
1. **Inventory & Classification**: Full classification of all repository files into build, runtime, deployment, migration, service worker, notification, analytics, dev-only, test-only, docs-only, and secrets.
2. **Deployment Contract**: Explicit document covering runtime version, build command, start command, required env var names, health endpoints, storage, and rollback.
3. **Artifact Strategy**: Multi-stage packaging and manifest-driven allowlisting.
4. **Manifest & Automation**: `release/production-manifest.json` and packaging verification tooling.
5. **Safety & Zero Disruption**: Maintain source repository integrity without destructive in-place deletions.
