# Company Skills & Autonomous Bot Roster

**Purpose:** A profitable company with strong *user engagement* needs a small set of
core functional skills. We researched what those are, then created one autonomous
**bot** per skill that performs real work against AbhiHub (Supabase + OpenRouter).

---

## 1. Research — what skills a company needs to run profitably

Sources reviewed: Lumen "Functional Areas of Business" (Management / Operations /
Finance / Marketing-Sales / R&D), RevOps Coop (Sales+Marketing+CS Ops), BCG & Salesforce
on AI agents, and SaaS retention literature (June, Paddle, HelpHero) on churn/engagement.

| # | Required skill (function) | Why it drives profit + engagement | Core responsibilities |
|---|---------------------------|-----------------------------------|-----------------------|
| 1 | **Growth / Marketing** | Brings in users cheaply; brand + demand. Without it, no pipeline. | SEO, content, social, referral loops, campaign analytics |
| 2 | **Customer Success / Engagement** | Retention is cheaper than acquisition; engaged users churn less and refer. | Onboarding, re-engagement of dormant users, NPS, health scoring |
| 3 | **Revenue / Monetization** | Turns engagement into money. AdSense + credits + premium. | Yield optimization, pricing, paywall/Ads, revenue reporting |
| 4 | **Operations / Finance** | Keeps the lights on and the cash positive. | Cost, infra health, anomalies, burn, runway, payouts |
| 5 | **Product / R&D** | Builds the loop users come back for. | Roadmap from feedback, bug triage, feature adoption |
| 6 | **Community** | Word-of-mouth engine; loyalty + UGC. | Forum/chat, advocates, peer matching, events |
| 7 | **Strategic Orchestration (CEO)** | Aligns the above; decides trade-offs. | KPI review, priority, cross-bot coordination |

> Engagement levers that came up repeatedly and are wired into the bots:
> guided onboarding, automated check-ins for dormant users, NPS/passive follow-up,
> loyalty/credit programs, personalization from product data, and early churn signals
> (login frequency ↓, feature usage ↓).

---

## 2. The bot roster (one role per skill)

Each bot is an autonomous `Bot` subclass. It runs a `run()` cycle, talks to a real
LLM via OpenRouter when `OPENROUTER_API_KEY` is set, calls AbhiHub APIs/SQL when
`SUPABASE_URL` is set, and falls back to **deterministic local logic** so it is always
runnable and testable offline.

| Bot | Class | Company skill | Key actions |
|-----|-------|---------------|-------------|
| 🚀 Growth Bot | `GrowthBot` | Marketing / Growth | SEO/canonical audit, content ideas, referral nudge, campaign readout |
| 💬 Engagement Bot | `EngagementBot` | Customer Success | dormant-user re-engagement, NPS survey, health scoring, onboarding tips |
| 💰 Revenue Bot | `RevenueBot` | Monetization | AdSense yield check, credit program stats, pricing/upsell signal |
| ⚙️ Ops Bot | `OpsBot` | Operations | infra health, cost anomalies, error/log scan |
| 📊 Finance Bot | `FinanceBot` | Finance | burn/runway estimate, payout calc (2% base AI / +0.5%/2yr cap 5%), anomalies |
| 🧭 Product Bot | `ProductBot` | Product / R&D | feedback triage, feature-adoption signal, roadmap draft |
| 🤝 Community Bot | `CommunityBot` | Community | top advocates, peer-matching nudge, moderation flags |
| 👑 CEO Bot | `CeoBot` | Orchestration | runs all bots, merges reports, sets weekly priority |

---

## 3. How to run

```bash
pip install requests            # only hard dependency for the bots

# list bots
python bots/run.py --list

# dry run (no network, deterministic) — safe to verify anytime
python bots/run.py --dry-run

# run one role
python bots/run.py --bot engagement

# full company cycle (all bots) — uses live APIs + LLM if env vars present
python bots/run.py --cycle
```

**Env (all optional — missing ones trigger safe fallback):**
- `OPENROUTER_API_KEY` — real LLM reasoning
- `SUPABASE_URL` / `SUPABASE_KEY` — live data
- `BASE_DOMAIN` — defaults to `abhihub.run.place`
- `API_BASE` — AbhiHub base URL (defaults to `https://{BASE_DOMAIN}`)

Reports are written to `bots/reports/` as both JSON and Markdown.

See `bots/README.md` for the full file map and the determinism contract.
