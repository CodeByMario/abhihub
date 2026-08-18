"""Finance Bot — Finance skill.

Researched: funding, budgets, cash flow, burn, runway, payouts.
Implements AbhiHub's revenue-share policy deterministically.

Policy: 2% base to AI models, +0.5% every 2 years, capped at 5%.
Remainder (no college share) to developer.
"""
from bot import Bot
import config
from datetime import datetime, timezone


class FinanceBot(Bot):
    name = "finance"
    role = "Finance"
    emoji = "📊"

    def run(self, ctx):
        r = self._report()
        # Estimate AI share based on platform age (founded 2025).
        founded = 2025
        now_year = datetime.now(timezone.utc).year
        years = max(0, now_year - founded)
        steps = years // 2
        ai_share = min(config.AI_BASE_SHARE + steps * config.AI_SHARE_STEP,
                       config.AI_SHARE_CAP)
        dev_share = 1.0 - ai_share

        gross = ctx.get("gross_revenue", 1000.0)  # placeholder; live via Supabase later
        r.add_metric("gross_revenue_est", gross)
        r.add_metric("ai_model_share_pct", round(ai_share * 100, 2))
        r.add_metric("developer_share_pct", round(dev_share * 100, 2))
        r.add_metric("ai_payout_est", round(gross * ai_share, 2))
        r.add_metric("developer_payout_est", round(gross * dev_share, 2))
        r.add_metric("college_share", 0.0)

        r.add_action("Compute payout split", "Per AbhiHub policy (no college share)")
        r.add_insight(
            f"AI models get {ai_share*100:.1f}% (base 2% + {steps} step(s) of 0.5%/2yr, "
            f"cap 5%). Developer gets the rest. College share = 0.")
        r.add_recommendation(
            "Wire live gross revenue from Supabase billing table to replace estimate.")
        r.save()
        return r
