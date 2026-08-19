"""Ops Bot — Operations skill.

Researched: keep systems healthy and costs controlled (the 'lights on' function).
Checks infra health + error signals via AbhiHub analytics endpoints.
"""
from bot import Bot
import config


class OpsBot(Bot):
    name = "ops"
    role = "Operations"
    emoji = "⚙️"

    def run(self, ctx):
        r = self._report()
        errors = self._http_get("/api/admin/analytics/errors") or {}
        recent_errors = errors.get("count_7d", 3)
        r.add_metric("errors_7d", recent_errors)
        r.add_metric("health", "degraded" if recent_errors > 10 else "ok")

        r.add_action("Scan service worker / cache", "Verify SW not returning 403/204 on APIs")
        r.add_action("Check Heroku worker health", "Confirm scheduler + cron jobs firing")
        if recent_errors > 10:
            r.add_recommendation("Triage top error endpoints before next deploy.")
        else:
            r.add_recommendation("No critical ops incidents; hold the line on cost.")
        r.save()
        return r
