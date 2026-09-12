# Implementation Plan: Cross-Platform Notification Reliability Hardening

**Track ID:** `notifications_cross_platform_20260911`  
**Status:** Completed / Ready for Review  

---

## Phase 1: Architecture & Provider Decoupling
- [x] Task: Formalize Provider-Independent Notification Service Layer
  - [x] Define `NotificationService` interface in `push_notifications.py`
  - [x] Encapsulate Web Push VAPID logic inside `WebPushAdapter`
  - [x] Add stub/extensibility hooks for future provider adapters (e.g., FCM / APNs)
- [x] Task: Phase Verification & Checkpoint
  - [x] Verify adapter isolation via unit test stubs

## Phase 2: Device Lifecycle, Subscriptions & Outbox Hardening
- [x] Task: Enhance Subscription Tracking & Pruning
  - [x] Ensure `save_push_subscription` records device metadata (`platform`, `browser`, `device_type`)
  - [x] Update `last_seen_at`, `last_success_at`, `last_failure_at` during dispatch cycles
  - [x] Verify HTTP 404/410 immediate pruning logic in `remove_subscription_by_endpoint`
- [x] Task: In-Memory & Cache Deduplication
  - [x] Enforce deduplication key evaluation (`user_id:tag:title`)
  - [x] Verify 30-second dedupe window and cache eviction rules
- [x] Task: Phase Verification & Checkpoint
  - [x] Run test suite against subscription lifecycle and deduplication

## Phase 3: Service Worker & Cross-Platform UX
- [x] Task: Service Worker Deep-Linking & Action Hardening
  - [x] Verify `/sw.js` route headers (`Service-Worker-Allowed: /`, no-cache)
  - [x] Verify notification click action handling (`open`, `dismiss`) and client window focus
  - [x] Ensure safe relative URL allowlisting in both client JS and Service Worker
- [x] Task: iOS PWA & Unsupported Browser Guidance
  - [x] Add subtle guidance in `/settings` for iOS Safari users regarding "Add to Home Screen" requirement
  - [x] Ensure in-app notification bell fallback renders seamlessly when push is denied/unsupported
- [x] Task: Phase Verification & Checkpoint
  - [x] Test Service Worker registration and click navigation in browser

## Phase 4: Automated Verification & Documentation
- [x] Task: Expand Test Suite
  - [x] Add unit tests for `NotificationService` dispatching and preference enforcement
  - [x] Add integration tests for `/api/push/*` routes with mock VAPID endpoints
  - [x] Verify zero regressions across `tests/test_notifications.py` and `tests/test_dashboard_auth.py`
- [x] Task: Complete Operational Runbooks
  - [x] Finalize `docs/notifications/production-runbook.md` with disaster recovery and provider rotation steps
  - [x] Finalize `docs/notifications/test-runbook.md`
- [x] Task: Phase Verification & Final Checkpoint
  - [x] Run full test suite: `pytest -q tests/test_notifications.py`
