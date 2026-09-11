# Implementation Plan: AbhiHub Production Deployment Packaging & Branch Isolation

## Phases

- [ ] **Phase 1: Inventory & Inspection Baseline**
  - [x] Complete workspace file inventory and classification (`docs/release/production-inventory.md`).
  - [x] Formulate deployment contract (`docs/release/deployment-contract.md`).
  - [ ] Present audit report, inclusion/exclusion list, artifact strategy, and risk assessment to user for gate approval.

- [ ] **Phase 2: Packaging Automation & Manifest Creation**
  - [ ] Create `release/production-manifest.json` with strict allowlist and rationale.
  - [ ] Create `.dockerignore` and multi-stage container / packaging script (`scripts/build-production-artifact.py`).
  - [ ] Create deployment and rollback runbooks (`docs/release/deployment-runbook.md`, `docs/release/rollback-runbook.md`).

- [ ] **Phase 3: Production Branch Preparation & Hardening**
  - [ ] Await user branch creation approval.
  - [ ] Create `release/production-deployment` from baseline commit.
  - [ ] Apply packaging files and ensure no secret / dev bloat is staged.

- [ ] **Phase 4: Artifact Inspection, Verification & Smoke Testing**
  - [ ] Build clean staging artifact via script.
  - [ ] Verify file count, size reduction, zero `.git`/`.env`/dev/test code presence.
  - [ ] Run health check and smoke test against packaged artifact.
  - [ ] Generate final release readiness report.
