# AbhiHub Analytics Rollout & Rollback Plan

**Version:** 1.0.0  
**Status:** Pre-Deployment Runbook  

---

## 1. Phased Rollout Strategy

The analytics overhaul follows a 4-phase safe rollout to prevent data disruptions or metric discontinuities:

### Phase 1: Local & Staging Validation (Complete Pre-Check)
- Deploy the updated `AbhiHubAnalytics` engine to staging.
- Open GA4 DebugView and test primary user journeys:
  1. Google Login & Email Login (confirm zero email/name leakage).
  2. PDF note viewer (confirm `content_viewed` + `content_engaged`).
  3. Bulk file upload (confirm `upload_started` + `upload_completed` with server confirmation).
  4. Search and filter actions (confirm query length tracking, no raw text).
- Validate that `tests/test_analytics_redesign.py` passes 100% of unit tests.

### Phase 2: Dual-Mode Compatibility (Shadow Rollout)
- Production templates run `AbhiHubAnalytics` with the legacy shim enabled.
- Legacy `window.AbhiHubTracking` calls are automatically mapped to canonical event schemas without breaking existing buttons.
- Monitor error telemetry on `/api/admin/analytics/errors` for 48 hours.

### Phase 3: Console Definitions & Full Cutover
- In Google Analytics Admin, create the custom dimensions and metrics specified in `docs/analytics/dashboard-spec.md`.
- Transition all internal dashboards to the canonical schema.

### Phase 4: Legacy Deprecation & Cleanup
- Remove deprecated backward-compatibility shims once all template partials are confirmed on the new schema.

---

## 2. Emergency Rollback Procedures

If unexpected client-side runtime errors, severe data discrepancy ($> 20\%$), or browser performance degradation occurs:

### Instant Client-Side Killswitch (Zero Deployment)
Set client-side analytics disable flag in template context or via environment variable:
```bash
# Disable GA4 dispatch without rolling back application code
export GA4_DISABLED=true
```

### Git Rollback Procedure
If code rollback is necessary:
1. Revert to previous analytics tag revision:
   ```bash
   git checkout HEAD~1 -- templates/google_tag.html static/js/analytics-helper.js static/login-auth.js
   ```
2. Re-run test suite:
   ```bash
   pytest tests/
   ```
3. Restart application service:
   ```bash
   pkill -f gunicorn || true
   ```
