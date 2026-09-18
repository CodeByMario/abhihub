# Track Spec: AI Tutor — Hybrid BYOK / Platform Key

## Overview
Extend the existing `/api/ask-paper` endpoint into a full pedagogical AI tutor.
Supports two tiers: free (platform key, hard daily cost ceiling) and BYOK (user's
own OpenRouter key, ceiling lifted). All guardrails (loop cap, content safety,
context compaction) apply to both tiers.

## Functional Requirements

### FR1 – Provider Abstraction (F3, F6)
- `LLMProvider` protocol + `OpenRouterAdapter` in `methods/ai_provider.py`.
- Core never imports `requests` or touches OpenRouter URLs directly.
- `ProviderResponse` dataclass is the only type crossing the boundary.
- Adapter strips any Bearer token from `raw_error` before returning.

### FR2 – Key Resolution (F5)
- Free tier: `os.getenv('OPENROUTER_API_KEY')`.
- BYOK tier: Fernet-decrypt `profiles.ai_key_enc` in-memory per request.
- `KeyInvalidError` on 401 — never silently falls back to platform key.
- `FERNET_KEY` env var validated at startup.

### FR3 – BYOK Key Management
- `POST /api/ai/key`: validate key with one cheap test call, Fernet-encrypt, persist to `profiles.ai_key_enc`.
- `DELETE /api/ai/key`: clear `ai_key_enc`, set `ai_plan='free'`.
- Minimal functional form in settings for testability; UI polish is a separate track.

### FR4 – Cost Governance (F9)
- `ai_usage_log` table: one row per turn (provider, model, tokens_in, tokens_out, cost_usd, duration_ms, mode, override_used, error_type).
- Compaction calls log their own row and count toward the daily ceiling.
- Free tier: sum `cost_usd` for today; if >= `AI_MAX_COST_USD_PER_DAY` → HTTP 402.
- **Known limitation**: read-then-write race allows slight ceiling overage (~1 concurrent request). Acceptable at MVP scale; use DB-level atomic counter if throughput requires it.
- BYOK tier: log only (no ceiling).
- `/api/ai/usage` GET: user's own aggregated daily usage.

### FR5 – Pedagogy (Socratic default)
- Scaffold mode ON by default. Direct mode via `?mode=direct` or session flag.
- `override_used=True` logged when `mode=direct`.
- Both system prompts include explicit content boundary clause (defense in depth beyond keyword filter).

### FR6 – Session Memory (F2)
- `tutor_sessions` table: `summary`, `topic_map JSONB`, `mode`, `turn_count`.
- Rolling window: last 6 turns verbatim (`AI_SESSION_WINDOW`).
- Compaction at threshold (default 10 turns): summarise oldest 4 turns → update `summary`.
- Pinned system prompt reconstructed fresh each turn — never evicted.
- `topic_map` shape: `{topic: {doc_id, confidence, last_seen_at}}` (per-document now, per-subject queryable later via query change).

### FR7 – Safety Guardrails (F4)
- `check_input()`: keyword/pattern filter for age-inappropriate + anti-verbatim-completion patterns. Borderline results logged to `ai_usage_log.safety_flag` column (flagged but passed through).
- `check_output()`: scan for injection artefacts; truncate suspicious role-switch patterns.
- Tool outputs (future) must use `role=tool` only — never injected into `role=system`.

### FR8 – Observability (F7)
- Structured row in `ai_usage_log` after every turn including failures.
- Error type recorded (`error_type TEXT`).

### FR9 – Error Taxonomy (F8)
- 5 typed errors: `ProviderError`, `RateLimitError`, `ContextLimitError`, `KeyInvalidError`, `CostCeilingError`.
- Recovery: RateLimit → next model; ContextLimit → compact+retry; KeyInvalid → 401 surface (NO fallback); CostCeiling → 402.

### FR10 – Loop Guard (F1)
- `AI_MAX_STEPS_PER_TURN=5` (env-configurable).
- Same-tool + same-args repeat → abort.

## Non-Functional Requirements
- No hardcoded secrets. No provider-specific objects in core flow.
- All new env vars have sane defaults except `FERNET_KEY` (required for BYOK).
- Ponytail: stdlib first, no unrequested abstractions.

## Out of Scope (Explicitly Deferred)
- **G12**: Vision/OCR unification with `/api/extract-ocr` — deferred.
- **G13**: Streaming responses — deferred.
- Direct OpenAI/Anthropic/Gemini adapters — deferred (OpenRouter proxies them).
- Ollama/local model support — deferred indefinitely.
- Full `settings.html` BYOK UI redesign — separate follow-up track.

## Acceptance Criteria
- [ ] Free-tier user gets HTTP 402 when daily cost ceiling is hit.
- [ ] BYOK user with a bad key gets HTTP 401 with explanation, never falls back to platform key.
- [ ] Scaffold mode is ON by default; toggle persists in session.
- [ ] Every turn (success or failure) produces one `ai_usage_log` row.
- [ ] Compaction calls produce their own `ai_usage_log` row.
- [ ] `check_input` borderline results appear in `ai_usage_log.safety_flag`.
- [ ] No key value appears in any log line or API response.
- [ ] `add_quota_fields.sql` schema namespace bug noted in migration 028 PR comment.
