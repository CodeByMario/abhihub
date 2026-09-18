# Track Plan: AI Tutor — Hybrid BYOK / Platform Key

## Implementation Order (8 increments, each reviewed before next)

### Increment 1 — Migration 028
- [ ] Write `migrations/028_ai_tutor.sql`
  - [ ] `profiles`: add `ai_plan`, `ai_key_enc`, `ai_provider` (constrained CHECK)
  - [ ] Create `tutor_sessions` table with `topic_map JSONB`
  - [ ] Create `ai_usage_log` table with `safety_flag` column
  - [ ] Add `abhihub.` prefix to all DDL (fix schema namespace pattern)
  - [ ] PR comment noting `add_quota_fields.sql` namespace bug
- [ ] Phase Verification: SQL reviewed, ready to run against Supabase

### Increment 2 — `methods/ai_provider.py`
- [ ] `ProviderResponse` dataclass
- [ ] `LLMProvider` Protocol
- [ ] `ProviderError`, `RateLimitError`, `ContextLimitError`, `KeyInvalidError` exceptions
- [ ] `OpenRouterAdapter`: model fallback loop, key-stripped error, token/cost parsing
- [ ] Minimal `__main__` self-check (Ponytail test gate)
- [ ] Phase Verification: Ponytail review pass

### Increment 3 — `methods/ai_usage.py`
- [ ] `check_ceiling(user_id)` — sum today's cost vs env ceiling (race-condition comment)
- [ ] `log_turn(...)` — insert row to `ai_usage_log` (called by session AND compaction)
- [ ] `CostCeilingError` exception
- [ ] `get_user_usage(user_id, days=7)` — for `/api/ai/usage` endpoint
- [ ] Phase Verification: Ponytail review pass

### Increment 4 — Key Resolution + `/api/ai/key`
- [ ] `supabase_helper.py`: add `get_ai_profile()`, `set_ai_key_enc()`, `clear_ai_key()`
- [ ] Key resolution function in `ai_provider.py`: free → env key, byok → Fernet-decrypt
- [ ] FERNET_KEY startup validation
- [ ] `POST /api/ai/key` in `app.py`: validate key (cheap test call) → encrypt → persist
- [ ] `DELETE /api/ai/key` in `app.py`: clear key, set plan=free
- [ ] `.env.example` additions: `AI_MAX_COST_USD_PER_DAY`, `FERNET_KEY`, `AI_SESSION_WINDOW`, `AI_MAX_STEPS_PER_TURN`
- [ ] Phase Verification: Ponytail review pass; BYOK key roundtrip testable

### Increment 5 — `methods/ai_session.py`
- [ ] `get_or_create_session(user_id, doc_id)` → `tutor_sessions` row
- [ ] `build_context(session, doc_text)` — rolling window + pinned system prompt
- [ ] `compact_if_needed(session, provider, key)` — calls provider for summary, logs own `ai_usage_log` row via `log_turn()`
- [ ] `update_topic_map(session, turn_text)` — update JSONB
- [ ] `record_turn(session_id, turn_count)` — increment + update `last_active_at`
- [ ] Phase Verification: Ponytail review pass

### Increment 6 — `methods/ai_safety.py`
- [ ] `SafetyResult` dataclass (`passed: bool`, `flag: str | None`, `borderline: bool`)
- [ ] `check_input(question, session)` — keyword/pattern filter, borderline → `flag` set but `passed=True`
- [ ] `check_output(response)` — injection artefact scan
- [ ] Content boundary clause strings (injected into both scaffold + direct system prompts)
- [ ] Phase Verification: Ponytail review pass

### Increment 7 — Rewire `/api/ask-paper`
- [ ] Replace in-process `_chat_history` rate limiter with `check_ceiling()` from `ai_usage.py`
- [ ] Wire key resolution → `OpenRouterAdapter`
- [ ] Wire `ai_session`: get/create session, build context, compact if needed
- [ ] Wire `ai_safety`: check_input pre-call, check_output post-call
- [ ] Wire `log_turn()` after every call (success + failure)
- [ ] Socratic/direct mode routing via `session.mode`
- [ ] Typed error recovery (RateLimit→next model, ContextLimit→compact+retry, KeyInvalid→401, CostCeiling→402)
- [ ] Loop guard: `AI_MAX_STEPS_PER_TURN` respected
- [ ] Phase Verification: end-to-end test free-tier ceiling + BYOK bad key + scaffold mode

### Increment 8 — `/api/ai/usage` + Final Report
- [ ] `GET /api/ai/usage` handler (auth_required, own rows only)
- [ ] Final track report in `conductor/tracks/ai_tutor_20260918/report.md`:
  - [ ] Explicitly state G12 (vision/OCR unification) deferred
  - [ ] Explicitly state G13 (streaming) deferred
  - [ ] List changed files
  - [ ] Known limitations (race condition, UI polish deferred)
- [ ] Phase Verification: complete
