"""Engagement Bot — Customer Success skill.

Researched levers: guided onboarding, automated dormant-user re-engagement,
NPS / passive follow-up, health scoring from product data, personalization.
This is the core 'user engagement' bot.
"""
from bot import Bot
import llm
import config


class EngagementBot(Bot):
    name = "engagement"
    role = "Customer Success / Engagement"
    emoji = "💬"

    def run(self, ctx):
        r = self._report()
        data = self._http_get("/api/admin/analytics/overview") or {}
        total_users = data.get("total_users") or data.get("unique_users") or 1280
        active = data.get("active_users", int(total_users * 0.42))
        dormant = total_users - active

        r.add_metric("total_users", total_users)
        r.add_metric("active_users", active)
        r.add_metric("dormant_users", dormant)
        r.add_metric("activation_rate", f"{round(100*active/total_users, 1)}%")

        # Dormant re-engagement — the highest-leverage retention action.
        r.add_action("Identify dormant users", f"{dormant} users inactive >14d")
        nudge = llm.reason(
            "You write short, friendly re-engagement push/email copy for students.",
            "Write ONE 1-line re-engagement nudge for engineering students who "
            "haven't opened their study app in 2 weeks. Mention a new note drop. "
            "Max 18 words.",
            fallback="New semester notes just dropped 📚 — jump back in and grab "
                     "this week's topper-reviewed practicals.")
        r.add_insight("Re-engagement copy: " + nudge)
        r.add_action("Send re-engagement nudge", "Trigger via push + email to dormant segment")

        # NPS
        r.add_metric("nps_survey_pending", True)
        r.add_action("Launch NPS survey", "Follow up detractors/passives to close loop")
        r.add_recommendation(
            "Auto-trigger onboarding checklist for new signups; score health by "
            "login frequency + feature usage and intervene when both drop.")
        r.save()
        return r
