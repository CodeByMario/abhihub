# AbhiHub Autonomous Company Bots

A small "company in code": one autonomous bot per researched company skill, each
performing real work against AbhiHub (Supabase + OpenRouter) with a deterministic
fallback so it always runs and is testable.

## File map
- `config.py` — env + policy (canonical domain, revenue-share, model)
- `llm.py` — OpenRouter client + deterministic fallback (`reason`, `reason_json`)
- `bot.py` — `Bot` base, `Report`, `RunContext`
- `roles/` — one module per role: `growth, engagement, revenue, ops, finance, product, community, ceo`
- `run.py` — CLI runner
- `reports/` — generated `.json` + `.md` per bot, plus `company_consolidated.json`

## Determinism contract
- No `OPENROUTER_API_KEY` → `reason()` returns the supplied fallback (offline-safe).
- No `SUPABASE_URL`/`SUPABASE_KEY` → `_http_get()` returns `None` → bots use
  local estimates. The cycle still runs and writes reports.
- Both present → live LLM reasoning + live API data.

## Commands
```bash
python bots/run.py --list                 # show roster
python bots/run.py --dry-run              # all bots, no network
python bots/run.py --bot engagement       # one role
python bots/run.py --cycle                # CEO runs everyone + weekly priority
```

## Adding a bot
1. Create `roles/<name>.py` with a `class <Name>Bot(Bot)` implementing `run(ctx)`.
2. Register it in `roles/ceo.py` `ROSTER` and in `run.py` `BY_NAME`.
3. Run `--dry-run` to verify.
