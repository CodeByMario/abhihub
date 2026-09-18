# Track Report: AI Tutor — Hybrid BYOK / Platform Key
## Track ID: `ai_tutor_20260918` | Status: Complete

---

## Changed Files

| File | Type | What Changed |
|---|---|---|
| `migrations/028_ai_tutor.sql` | NEW | `profiles` AI columns, `tutor_sessions`, `ai_usage_log` with `safety_flag` |
| `methods/ai_provider.py` | NEW | `LLMProvider` protocol, `OpenRouterAdapter`, `ProviderResponse`, key resolution, typed errors, `validate_startup()` |
| `methods/ai_usage.py` | NEW | `check_ceiling()`, `log_turn()` (incl. `mode='compaction'`), `get_user_usage()`, `CostCeilingError` |
| `methods/ai_session.py` | NEW | `get_or_create_session()`, `build_context()`, `compact_if_needed()`, `record_turn()`, `update_topic_map()` |
| `methods/ai_safety.py` | NEW | `check_input()`, `check_output()`, `clean_output()`, `SCAFFOLD_SYSTEM`, `DIRECT_SYSTEM` (with content boundary clauses) |
| `methods/supabase_helper.py` | EXTEND | `get_ai_profile()`, `set_ai_key_enc()`, `clear_ai_key()` |
| `app.py` | EXTEND | `/api/ask-paper` rewired; `POST /api/ai/key`, `DELETE /api/ai/key`, `GET /api/ai/usage` added |
| `requirements.txt` | EXTEND | `cryptography>=42.0.0` |
| `.env.example` | EXTEND | `FERNET_KEY`, `AI_MAX_COST_USD_PER_DAY`, `AI_SESSION_WINDOW`, `AI_MAX_STEPS_PER_TURN` |

---

## Spec Acceptance Criteria — Verification

| Criterion | Status | Evidence |
|---|---|---|
| Free-tier user gets HTTP 402 when daily cost ceiling is hit | ✅ | `check_ceiling()` → `CostCeilingError` → 402 in ask-paper |
| BYOK user with a bad key gets HTTP 401, never falls back | ✅ | `KeyInvalidError` path → 401; no fallback branch |
| Scaffold mode ON by default; toggle persists in session | ✅ | `mode_req > session.mode > 'scaffold'`; `record_turn` updates session |
| Every turn produces one `ai_usage_log` row | ✅ | `log_turn()` called on success, KeyInvalid, ProviderError, UnexpectedError paths |
| Compaction calls produce their own `ai_usage_log` row | ✅ | `compact_if_needed()` calls `log_turn(mode='compaction')` — amendment 2 |
| `check_input` borderline results appear in `safety_flag` | ✅ | `safety_in.flag` passed to `log_turn()` — amendment 3 |
| No key value in any log line or API response | ✅ | `_strip_key()` in adapter; `KeyInvalidError` message is static string; key vars never in f-strings |
| Schema namespace bug noted | ✅ | SQL comment in migration 028 headers |

---

## Gaps Closed in This Track

| Gap | Resolution |
|---|---|
| G1 — in-process rate limiter | Replaced with Supabase `ai_usage_log` cost ceiling |
| G2 — no BYOK distinction in rate limiter | `check_ceiling()` only applies to free tier; BYOK skips ceiling |
| G3 — no BYOK path | `resolve_provider()` + `profiles.ai_plan` + `/api/ai/key` endpoints |
| G4 — no session memory | `tutor_sessions` + `build_context()` + `compact_if_needed()` |
| G5 — no pedagogy layer | `SCAFFOLD_SYSTEM` (default ON) + `DIRECT_SYSTEM` (toggle), `override_used` logged |
| G6 — no cost accounting | `ai_usage_log` row per turn with `cost_usd`, `tokens_in/out` |
| G7 — arbitrary 4000-char slice | Now `doc_text[:3000]` inside `build_context()` (token-window aware) |
| G8 — no content safety | `check_input()` + `check_output()` + `clean_output()` + content boundary clauses |
| G9 — generic error strings | 5 typed error classes, each with its own HTTP status and user-safe message |
| G10 — no loop guard | `AI_MAX_STEPS_PER_TURN` env var, while loop with `step < max_steps` |
| G11 — no structured observability | Structured `ai_usage_log` row per turn; queryable by user, date, error_type |

---

## ⚠️ Explicitly Deferred — NOT Silently Dropped

### G12 — Vision/OCR Unification
`/api/extract-ocr` and `/api/ask-paper` remain separate code paths.
Unification (one shared extraction pipeline) is deferred out of this track.
The ask-paper handler uses pypdf/fitz text extraction only; the existing OCR
fallback within ask-paper (fitz page render) is preserved but not unified with
the standalone `/api/extract-ocr` endpoint.
**Action required**: open a follow-up track `ai_ocr_unify` when OCR is a priority.

### G13 — Streaming Responses
All LLM responses are buffered (full response before return).
Streaming via Server-Sent Events or chunked transfer is deferred.
**Action required**: open a follow-up track `ai_streaming` when UX requires it.

---

## Known Limitations

| Limitation | Detail | Mitigation |
|---|---|---|
| Read-then-write race on `check_ceiling()` | A user could overshoot by ~1 concurrent request (~$0.02 exposure) | Acceptable at MVP. Replace with DB-level atomic counter if needed. Flagged in code. |
| BYOK key validation makes a real API call | ~1 token call to verify. Network error during validation logs a warning but doesn't block save. | Intentional — fail-open on network errors; fail-closed on 401. |
| BYOK UI is minimal | Two API endpoints are live and testable; `settings.html` integration is a separate track. | Functional but unstyled. |
| `topic_map` updates require extracting topics | Current implementation only supports explicit `update_topic_map()` calls; automatic topic extraction from turn text is not implemented. | Call it explicitly where topic context is available; full NLP extraction is a future track. |

---

## Commit History (this track)

```
chore(conductor): initialize track 'ai_tutor_20260918'
feat(ai-tutor): migration 028 — profiles AI columns, tutor_sessions, ai_usage_log
feat(ai-tutor): ai_provider.py — LLMProvider protocol, OpenRouterAdapter, key resolution (F3,F5,F6,F8)
feat(ai-tutor): ai_usage.py — cost ceiling check, log_turn (incl. compaction), usage query (F9)
feat(ai-tutor): key resolution, /api/ai/key POST+DELETE with validate-on-save, /api/ai/usage, Fernet encryption (F5, amendment 4)
feat(ai-tutor): ai_session.py — rolling window, compaction with log_turn, topic_map, pinned prompt (F2, amendment 2)
feat(ai-tutor): ai_safety.py — hard-block, borderline flag+pass, output scan, defense-in-depth prompt clauses (F4, amendment 3)
feat(ai-tutor): rewire /api/ask-paper — cost ceiling, safety, session, typed errors, Socratic mode, usage logging (G1,G2,G3,G4,G5,G6,G8,G9,F1,F8)
```
