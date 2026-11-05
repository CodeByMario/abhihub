# Tarika AI: One-Time Setup, Tracking and Reverification Guide

**Project:** AbhiHub, Tarika AI (free-tier multi-provider router + WebLLM)
**Purpose:** One file to (1) set everything up once, (2) verify it works, (3) keep records, (4) re-check on a schedule.

> **How to use this file**
> 1. Do **Section 2** top to bottom, once. Tick each box as you go.
> 2. Run the **Section 3** verification. If all pass, setup is locked and never repeated.
> 3. After that, only use **Sections 4 and 5** (records and routine checks).
> 4. Free-tier limits change without notice. Never trust a number in this file. Always copy the current value from the provider dashboard into your records (Section 4).

---

## 0. Progress Dashboard

Update this block weekly. Copy the date and fill in.

| Area | Status | Date done | Notes |
|---|---|---|---|
| Accounts and keys | ✅ Done | 2026-10-11 | OpenRouter & Gemini live verified (HTTP 200) |
| `.env` file | ✅ Done | 2026-10-11 | `FERNET_KEY` and provider credentials configured |
| Database migration | ✅ Done | 2026-10-11 | Executed in Supabase `abhihub` schema |
| First catalog sync | ✅ Done | 2026-10-11 | 19 live `free_verified` models synced |
| Router and safety wiring | ✅ Done | 2026-10-11 | Multi-provider BYOK & RLS verified |
| WebLLM frontend | ✅ Done | 2026-10-11 | Edge engine in `static/js/ai/` |
| Verification passed | ✅ Done | 2026-10-11 | All health checks and catalog sync passed |
| Setup locked | ✅ Done | 2026-10-11 | `setup_completed` locked in `ai_config` |



---

## 1. What You Are Building (one screen summary)

```
User message
  → safety check (ai_safety)         → rate limit / quota (ai_usage)
  → cache (exact, then semantic)     → intent classifier (rules → embeddings → tiny LLM)
  → router:  tool (no LLM) | WebLLM on device | free cloud chain | BYOK
  → stream answer → output filter → usage log
```

Two live systems keep it free:

| System | Job |
|---|---|
| **Model Catalog Sync** | Knows which models are free right now. A model that turns paid is never routed. |
| **Device Capability Engine** | Picks the biggest WebLLM model each user's device can run, with one-click enable. |

**Free-only rule:** only models with status `free_verified` are routed (BYOK users excepted, since it is their own money).

---

## 2. One-Time Setup

Estimated time: 60–90 minutes. Do not skip steps. Each step ends with a **✔ Check** so you know it worked.

### Step A: Create accounts and keys (≈20 min)

Create **one** account per provider. Do not create multiple accounts per provider to get extra quota. That commonly violates provider terms and risks bans.

| # | Provider | Required? | Where to get a key | Key saved in `.env` as | Done |
|---|---|---|---|---|---|
| 1 | OpenRouter | **Required** (live pricing source) | openrouter.ai → Keys | `OPENROUTER_API_KEY` | ☐ |
| 2 | Google AI Studio (Gemini) | **Required** (vision, long context, Hindi/Marathi) | aistudio.google.com → Get API key | `GEMINI_API_KEY` | ☐ |
| 3 | Groq | Recommended (fast chat) | console.groq.com → API Keys | `GROQ_API_KEY` | ☐ |
| 4 | Cerebras | Optional | cloud.cerebras.ai | `CEREBRAS_API_KEY` | ☐ |
| 5 | Mistral | Optional | console.mistral.ai | `MISTRAL_API_KEY` | ☐ |
| 6 | Others (GitHub Models, NVIDIA NIM, Cloudflare Workers AI, Hugging Face) | Optional | Provider dashboards | See `.env` template | ☐ |

**Safety rules while creating accounts**
- ☐ Do **not** add a credit card or billing to any project where you want free-only usage. No billing means no surprise charge.
- ☐ On Google, keep Cloud Billing disabled for the AI Studio project.
- ☐ On OpenRouter, do not add credits unless you intentionally want paid fallbacks. (Note: some providers raise free limits if you hold a small balance. Check their current rules and decide on purpose.)
- ☐ Store keys in a password manager, never in Git.

✔ **Check:** You have at least keys #1 and #2.

### Step B: Create the `.env` file (≈5 min)

Create `.env` in the backend root. Add `.env` to `.gitignore` first.

```bash
# ---------- Providers (leave blank to disable) ----------
OPENROUTER_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
CEREBRAS_API_KEY=
MISTRAL_API_KEY=

# ---------- Infra ----------
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=        # server only, never ship to the browser
FERNET_KEY=                       # generated once, never change

# ---------- Policy ----------
CATALOG_MAX_STALE_MINUTES=30
FREE_ONLY=true
GUEST_QUOTA_SHARE=0.30            # share of daily quota reserved for guests
RATE_LIMIT_AUTH_PER_MIN=25
RATE_LIMIT_GUEST_PER_MIN=6

# ---------- Alerts (pick at least one) ----------
ALERT_TELEGRAM_BOT_TOKEN=
ALERT_TELEGRAM_CHAT_ID=
ALERT_EMAIL_TO=
```

Generate the BYOK encryption key once:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> ⚠️ Back up `FERNET_KEY`. If you lose or change it, every stored user key becomes unreadable.

✔ **Check:** `.env` exists, is in `.gitignore`, and `FERNET_KEY` is saved in your password manager.


### Step C: Run the database migration (≈5 min)

Open Supabase → SQL Editor → paste and run **once**. It is safe to re-run (`if not exists`).

-- Refer to scripts/create_tarika_tracking_tables.sql for the complete idempotent script.
-- Includes: user_ai_keys (per-user encrypted keys), model_catalog, ai_usage_log, and strict RLS policies.
```

See [scripts/create_tarika_tracking_tables.sql](file:///e:/Users/abhihub/New%20folder/abhihub/scripts/create_tarika_tracking_tables.sql) for the complete executable SQL migration.


✔ **Check:** run `select * from v_model_health;`. It returns without error (empty is fine).

### Step D: Run the one-time setup script (≈10 min)

Save as `scripts/tarika_setup.py`. It validates keys, runs the first catalog sync, and writes a **lock** so setup never has to be repeated.

```python
"""Tarika AI one-time setup. Safe to re-run: exits early once locked."""
import os, sys, httpx
from datetime import datetime, timezone
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

def done():
    r = db.table("ai_config").select("value").eq("key", "setup_completed").execute()
    return bool(r.data and r.data[0]["value"].get("ok"))

if done() and "--force" not in sys.argv:
    print("Setup already completed. Use --force to re-run."); sys.exit(0)

def log(name, ok, details=""):
    db.table("ai_setup_checks").insert(
        {"check_name": name, "passed": ok, "details": details[:500]}).execute()
    print(("PASS " if ok else "FAIL ") + name, details)
    return ok

# Verify these endpoints in each provider's docs before first run.
PROVIDERS = {
  "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/models", "bearer", True),
  "gemini":     ("GEMINI_API_KEY",
                 "https://generativelanguage.googleapis.com/v1beta/models?key={key}", "query", True),
  "groq":       ("GROQ_API_KEY", "https://api.groq.com/openai/v1/models", "bearer", False),
  "cerebras":   ("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1/models", "bearer", False),
  "mistral":    ("MISTRAL_API_KEY", "https://api.mistral.ai/v1/models", "bearer", False),
}

required_ok = True
for name, (env, url, auth, required) in PROVIDERS.items():
    key = os.getenv(env, "")
    if not key:
        ok = log(f"key:{name}", not required, "missing" + (" (REQUIRED)" if required else " (optional, skipped)"))
        required_ok &= ok; continue
    try:
        headers = {"Authorization": f"Bearer {key}"} if auth == "bearer" else {}
        r = httpx.get(url.format(key=key), headers=headers, timeout=20)
        ok = log(f"key:{name}", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        ok = log(f"key:{name}", False, str(e))
    required_ok &= (ok or not required)

enc_ok = log("fernet_key", bool(os.getenv("BYOK_FERNET_KEY")))
tables_ok = True
for t in ["model_catalog", "model_status_events", "ai_usage_log", "ai_config"]:
    try: db.table(t).select("*").limit(1).execute()
    except Exception as e: tables_ok = log(f"table:{t}", False, str(e)); continue
    log(f"table:{t}", True)

# First sync (use your real sync function from the router code)
try:
    from services.catalog_sync import sync_all   # <- from the earlier plan
    import asyncio; asyncio.run(sync_all())
    n = len(db.table("model_catalog").select("id").eq("status", "free_verified").execute().data)
    sync_ok = log("first_sync", n > 0, f"{n} free_verified models")
except Exception as e:
    sync_ok = log("first_sync", False, str(e))

if required_ok and enc_ok and tables_ok and sync_ok:
    db.table("ai_config").upsert({"key": "setup_completed", "value":
        {"ok": True, "at": datetime.now(timezone.utc).isoformat()}}).execute()
    print("\n✅ SETUP COMPLETE and locked. You never need to run this again.")
else:
    print("\n❌ Fix the FAIL lines above, then re-run. Nothing was locked.")
```

Run it:

```bash
pip install supabase python-dotenv httpx cryptography
python scripts/tarika_setup.py
```

✔ **Check:** the last line says `SETUP COMPLETE and locked`.

### Step E: Turn on the scheduled jobs (≈10 min)

These keep the status of every model current without any manual work. Create them **once** (Supabase pg_cron, Render/Railway cron, GitHub Actions, or a plain cron).

| Job | Schedule | What it does | Done |
|---|---|---|---|
| `sync_openrouter` | hourly | Refresh free/paid status from live pricing | ☐ |
| `sync_others` | every 6 h | Refresh model lists for Gemini, Groq, etc. | ☐ |
| `canary_probe` | daily, off-peak | 1 tiny request per active model (`max_tokens: 5`) | ☐ |
| `reset_quota_counters` | daily at each provider's reset time | Resets RPD counters | ☐ |
| `weekly_report` | Monday | Summary of v_free_ratio, status events, incidents | ☐ |

Example GitHub Actions cron (hourly sync):

```yaml
on:
  schedule: [{ cron: "7 * * * *" }]
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt && python -m jobs.sync_openrouter
        env: { OPENROUTER_API_KEY: "${{ secrets.OPENROUTER_API_KEY }}", SUPABASE_URL: "${{ secrets.SUPABASE_URL }}", SUPABASE_SERVICE_ROLE_KEY: "${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}" }
```

✔ **Check:** after one hour, `select max(last_synced_at) from model_catalog;` shows a fresh time.

### Step F: Install WebLLM on the frontend (≈15 min)

```bash
npm i @mlc-ai/web-llm
```

Create three files (code is in the previous plan, Parts 2–3):

| File | Purpose | Done |
|---|---|---|
| `llm.worker.js` | Runs the model off the UI thread | ☐ |
| `deviceProbe.js` | `probeDevice()` + `pickModel()` + `benchmark()` | ☐ |
| `OfflineAISetup.jsx` | One-screen wizard (recommend → download → test) | ☐ |

Rules to keep the setup one-time **for each user** too:
- ☐ Store `{modelId, tier, tps, setupDone: true}` in `localStorage`. Never re-probe unless the browser or GPU changes or the user taps "Re-check".
- ☐ Call `navigator.storage.persist()` after opt-in so downloaded weights are not evicted.
- ☐ Default to **Wi-Fi only** download. Show size and time before downloading.
- ☐ Never auto-download on mobile data.
- ☐ Settings page has: Auto / Always cloud / Always local, Delete offline model, Private mode.

✔ **Check:** on a WebGPU laptop, the wizard shows a recommended model, downloads it once, passes the "Hi!" test, and works with Wi-Fi off after a reload.

---

## 3. First Verification (run once, right after setup)

Tick all of these. If any fails, see Section 7.

### 3.1 Backend

| # | Test | Expected | Pass |
|---|---|---|---|
| 1 | `select * from ai_config where key='setup_completed'` | one row, `ok: true` | ☐ |
| 2 | `select count(*) from model_catalog where status='free_verified'` | > 0 | ☐ |
| 3 | Manually set one model to `paid`, send a chat | That model is **not** used | ☐ |
| 4 | Force a 429 (temporarily use a bad key or a tiny rpm limit) | Model enters `cooldown`, next provider answers | ☐ |
| 5 | Set `CATALOG_MAX_STALE_MINUTES=0` briefly | Non-BYOK requests get the "busy" message instead of hitting a stale model, then restore it | ☐ |
| 6 | Send the same question twice | Second call shows `cache_hit = true` in `ai_usage_log` | ☐ |
| 7 | Send a prompt-injection string | Blocked by `ai_safety` before any model call | ☐ |
| 8 | Guest sends 7 messages in one minute | 7th is rate limited | ☐ |
| 9 | Ask "open my notes" | Handled by tool, `route = tool`, no LLM tokens | ☐ |
| 10 | Add a BYOK key | Stored encrypted (check the DB value is not plaintext), limits lifted | ☐ |

### 3.2 Routing by message type

Send each message and confirm the route in `ai_usage_log`.

| Message type | Example | Expected route | Pass |
|---|---|---|---|
| Greeting | "hi" | template or WebLLM | ☐ |
| Navigation | "open DBMS notes" | tool | ☐ |
| PYQ search | "DBMS PYQ 2023" | tool (DB), no LLM | ☐ |
| Simple Q&A | "what is normalization?" | WebLLM, else small cloud | ☐ |
| Reasoning/math | "solve this probability problem…" | Gemini or large free model | ☐ |
| Hindi/Marathi | "नॉर्मलायझेशन म्हणजे काय?" | Gemini | ☐ |
| Image or scan | upload a question paper photo | OCR then Gemini vision | ☐ |
| Long PDF | upload a 50-page PDF | Gemini long context or chunk and retrieve | ☐ |

### 3.3 Device matrix (fill in as you test)

| Device / browser | WebGPU | Tier | Model picked | Tokens/s | Result | Date |
|---|---|---|---|---|---|---|
| Low-end Android, Chrome | | | | | | |
| Mid Android, Chrome | | | | | | |
| Windows laptop, integrated GPU | | | | | | |
| Laptop, discrete GPU | | | | | | |
| iPhone, Safari | | | | | | |
| Firefox desktop | | | | | | |
| Offline mid-download (resume) | | | | | | |

**Pass rule:** every device ends in a sensible tier, nothing crashes, and T0 devices cleanly fall back to cloud.

✔ **When every box above is ticked, setup is finished. Record the date in Section 0.**

---

## 4. Record-Keeping Templates

Keep these in `/docs/ai-records/` (one file each) or a Notion/Sheets tab. Copy a template row, never rewrite old rows.

### 4.1 Provider Registry (update when you change anything)

| Provider | Account email | Key created | Key rotated | Free-tier terms URL | Billing disabled? | Daily limit (copied from dashboard) | Date checked | Notes |
|---|---|---|---|---|---|---|---|---|
| OpenRouter | | | | | ☐ yes | | | |
| Gemini | | | | | ☐ yes | | | |
| Groq | | | | | ☐ yes | | | |
| Cerebras | | | | | ☐ yes | | | |
| Mistral | | | | | ☐ yes | | | |

### 4.2 Model Status Log (the DB does this automatically; keep manual notes only for decisions)

| Date | Model ID | Old → New status | Cause (sync / 402 / canary / announcement) | Action taken |
|---|---|---|---|---|
| | | | | |

Auto query:

```sql
select created_at, model_id, old_status, new_status, reason
from model_status_events order by created_at desc limit 50;
```

### 4.3 Quota Observations (limits you actually saw, not assumed)

| Date | Provider / model | RPM seen | RPD seen | Source (dashboard / header / 429) |
|---|---|---|---|---|
| | | | | |

### 4.4 Incident Log

| Date | Severity | What happened | Root cause | Fix | Prevention | Resolved |
|---|---|---|---|---|---|---|
| | | | | | | ☐ |

Insert to DB for a permanent record:

```sql
insert into ai_incidents(severity,title,details) values ('warn','Model X turned paid','Detected by hourly sync; auto-disabled');
```

### 4.5 Decision Log (why you chose things)

| Date | Decision | Options considered | Reason | Review date |
|---|---|---|---|---|
| | e.g. "Gemini for Hindi/Marathi complex queries" | Gemini vs Llama free | Better multilingual quality | |

### 4.6 Change Log

| Date | Version | Change | By |
|---|---|---|---|
| | v1.0 | Initial setup completed | |

### 4.7 Key Rotation Tracker

| Provider | Last rotated | Next due (every 90 days) | Done |
|---|---|---|---|
| | | | ☐ |

---

## 5. Reverification Routine

### 5.1 Automatic (no work from you)

| What | How | You are alerted when |
|---|---|---|
| Free vs paid status | Hourly and 6-hourly sync, plus per-response cost check | Any model flips to `paid` or `deprecated` |
| Silent breakage | Daily canary request | A canary fails twice in a row |
| Stale catalog | `CATALOG_MAX_STALE_MINUTES` guard | Sync has not succeeded for 30 min |
| Abuse or runaway use | Daily provider ceiling and kill switch | A provider reaches 80% of its daily ceiling |

### 5.2 Daily (2 min)

- ☐ Check alerts channel (Telegram/email).
- ☐ Run:

```sql
select * from v_model_health;
select * from v_free_ratio limit 7;
```

- ☐ Any provider with 0 `free_verified` models? Investigate that day.

### 5.3 Weekly (10 min, Monday)

- ☐ `select * from v_daily_usage limit 50;` and look at the 429 rate per provider (target: under 5%).
- ☐ Read the week's `model_status_events`. Add any lesson to the Decision Log.
- ☐ Check thumbs-up rate: local vs cloud routes.
- ☐ Review `device_telemetry`: `select tier, round(avg(tps),1) tps, count(*) from device_telemetry group by tier;`
- ☐ Review open incidents. Close or escalate.

### 5.4 Monthly (30 min)

- ☐ Open each provider's pricing and terms page. Compare with Provider Registry (4.1). Update limits and date checked.
- ☐ Confirm **billing is still disabled** where free-only is intended.
- ☐ Review the WebLLM model list from the `@mlc-ai/web-llm` release notes. Update `pickModel` family preference if better models were added.
- ☐ Review the free-ratio target: **40–60% of requests with zero cloud tokens**. If lower, check cache hit rate and intent rules.
- ☐ Back up: export `ai_usage_log`, `model_status_events`, `ai_incidents` to CSV.

### 5.5 Quarterly (1 hour)

- ☐ Rotate all provider keys (and update the Key Rotation Tracker).
- ☐ **Do not rotate `BYOK_FERNET_KEY`** without a re-encryption migration.
- ☐ Re-run the Section 3 test table end to end.
- ☐ Re-test the device matrix on at least two real devices.
- ☐ Archive `ai_usage_log` rows older than 90 days.

### 5.6 After any change (deploy, new provider, new model family)

- ☐ Re-run Section 3.1 tests 3, 4, 5 and 9 (the money-safety tests).
- ☐ Add a line to the Change Log.

---

## 6. Key Metrics (copy into your weekly note)

| Metric | Target | This week |
|---|---|---|
| % requests with zero cloud tokens | 40–60% | |
| Requests that hit a paid model | **0** | |
| Status changes caught before a user hit them | 100% | |
| 429 rate (overall) | < 5% | |
| p50 / p95 latency | | |
| WebLLM setup completion rate | > 60% of eligible devices | |
| Median local tokens/s (T1 / T2 / T3 / T4) | | |
| Local → cloud escalation rate | < 30% | |
| Thumbs-up: local vs cloud | similar | |
| Equivalent paid cost saved (USD) | tracking only | |

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Setup script says `FAIL key:openrouter HTTP 401` | Wrong or extra spaces in key | Re-copy key into `.env`, no quotes or spaces |
| `FAIL first_sync` | Network blocked or table missing | Check Step C ran; check outbound network access |
| Every request says "busy" | Catalog stale or all models in cooldown | Run the sync job manually; check `v_model_health` |
| Model keeps going to `cooldown` | Real free limit is lower than configured | Lower its `rpm`/`rpd` in `model_catalog`, log in 4.3 |
| A model works but is marked `paid` | Provider pricing field changed shape | Inspect the raw model response, adjust `is_free` logic |
| WebLLM wizard shows Tier 0 on a good laptop | Browser lacks WebGPU or it is disabled | Use latest Chrome/Edge; check `chrome://gpu` |
| Download restarts from zero | Storage evicted or private window | Call `navigator.storage.persist()`; avoid incognito |
| Phone crashes while loading model | Memory budget too high | Lower the mobile cap in `probeDevice`; log `outcome='failed'` |
| Local answers are poor in Hindi/Marathi | Small model language limits | Route non-English complex intents to Gemini |
| BYOK key rejected | Provider key invalid or not enabled | Re-validate with a model-list call before saving |
| Setup runs again every time | Lock row missing | Check `ai_config` for `setup_completed`; look for FAIL lines |

---

## 8. Definition of Done

Setup is complete and one-time when **all** are true:

- ☐ `ai_config.setup_completed.ok = true`
- ☐ At least 2 providers verified, including OpenRouter and Gemini
- ☐ Scheduled jobs running (Step E all ticked)
- ☐ Section 3 tests all ticked
- ☐ Alerts proven to arrive (flip a test model to `paid` and receive the message)
- ☐ Provider Registry (4.1) filled in with the dates and limits checked
- ☐ A user can enable offline AI in two taps and it works after a reload with Wi-Fi off
- ☐ Zero requests to paid models in `ai_usage_log` for 7 days

**Signed off by:** ____________  **Date:** ____________

---

## 9. Quick Reference

```sql
-- What is routable right now?
select id, health, rpm, rpd from model_catalog
where status='free_verified' and (cooldown_until is null or cooldown_until < now());

-- Panic button: stop one provider
insert into ai_config(key,value) values ('kill:groq','{"on":true}')
on conflict (key) do update set value='{"on":true}';

-- Did anything paid get used?
select * from ai_usage_log where model_id in
  (select id from model_catalog where status='paid') order by created_at desc limit 20;

-- Re-run setup deliberately
python scripts/tarika_setup.py --force
```

*Keep this file in your repo as `/docs/TARIKA_AI_SETUP_AND_TRACKER.md` and commit every update to the Change Log.*
