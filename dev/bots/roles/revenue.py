"""Revenue Bot — Monetization skill.

Researched: AdSense yield, pricing/upsell, credit programs, revenue reporting.
Maps to AbhiHub /api/monetization/* and the credit economy.
"""
from bot import Bot
import llm
import config


class RevenueBot(Bot):
    name = "revenue"
    role = "Monetization / Revenue"
    emoji = "💰"

    def run(self, ctx):
        r = self._report()
        # Live monetization signal if available.
        waitlist = self._http_get("/api/monetization/waitlist") or {}
        r.add_metric("waitlist_size", waitlist.get("count", "n/a"))

        # Credit program (the engagement->revenue loop).
        r.add_metric("credit_earn_upload", 10)
        r.add_metric("credit_earn_referral", 50)
        r.add_action("Audit credit ledger", "Ensure earn/burn balances prevent inflation")
        r.add_insight("Credits tie engagement to value: upload + referrals earn, "
                      "premium features burn.")

        # Pricing signal — LLM on real data if present.
        pricing = llm.reason(
            "You are a monetization analyst for an education SaaS with a free "
            "ad-supported tier and a credit/Premium upsell.",
            "Given an ad-supported free tier and a 50-credit referral reward, "
            "name 2 pricing levers to lift revenue without hurting engagement. "
            "One line each.",
            fallback="- Introduce 'Remove Ads' weekly pass (burn credits)\n"
                     "- Tiered referral bonus for 5+ invited active peers")
        r.add_insight("Pricing levers:\n" + pricing)
        r.add_recommendation(
            "Track AdSense RPM by page; shift ad slots to high-dwell PDF viewer pages.")
        r.save()
        return r
