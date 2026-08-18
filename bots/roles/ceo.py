"""CEO Bot — Strategic Orchestration skill.

Runs every other bot, merges their reports, and sets the weekly priority.
This is the only bot that depends on the others; it holds the RunContext.
"""
import json
import os
from datetime import datetime, timezone

from bot import Bot, RunContext, Report
import config

# Import role bots (lazy-friendly: they only import siblings).
from roles.growth import GrowthBot
from roles.engagement import EngagementBot
from roles.revenue import RevenueBot
from roles.ops import OpsBot
from roles.finance import FinanceBot
from roles.product import ProductBot
from roles.community import CommunityBot

ROSTER = [
    GrowthBot, EngagementBot, RevenueBot, OpsBot,
    FinanceBot, ProductBot, CommunityBot,
]


class CeoBot(Bot):
    name = "ceo"
    role = "Strategic Orchestration"
    emoji = "👑"

    def __init__(self):
        self.subbots = [b() for b in ROSTER]

    def run(self, ctx: RunContext):
        r = self._report()
        ctx.reports["ceo"] = r
        for bot in self.subbots:
            sub = bot.run(ctx)
            ctx.reports[bot.name] = sub
            r.add_action(f"Ran {bot.name} ({bot.role})",
                         f"{len(sub.actions)} actions, {len(sub.recommendations)} recs")

        # Merge cross-bot signals into a weekly priority.
        eng = ctx.reports.get("engagement")
        fin = ctx.reports.get("finance")
        dormant = (eng.metrics.get("dormant_users") if eng else None)
        priority = []
        if dormant and dormant > 0:
            priority.append(
                f"P1 Re-engage {dormant} dormant users (highest ROI retention lever).")
        priority.append("P2 Ship 'Exam Pack' auto-collection (product+growth synergy).")
        priority.append("P3 Audit AdSense RPM on PDF viewer pages (revenue).")
        priority.append("P4 Keep ops error rate flat; no unnecessary deploys.")

        r.add_metric("bots_run", len(self.subbots))
        r.add_metric("weekly_priority_count", len(priority))
        for p in priority:
            r.add_recommendation(p)
        r.add_insight("Weekly priority assembled from all role bots.")
        r.save()

        # Write a consolidated company report.
        consolidated = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bots": {name: rep.to_dict() for name, rep in ctx.reports.items()},
            "weekly_priority": priority,
        }
        path = os.path.join(config.REPORTS_DIR, "company_consolidated.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(consolidated, fh, indent=2, ensure_ascii=False)
        return r
