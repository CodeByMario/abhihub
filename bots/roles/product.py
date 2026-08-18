"""Product Bot — Product / R&D skill.

Researched: roadmap from feedback, feature-adoption signal, bug triage.
Turns engagement data + feedback into a prioritized roadmap.
"""
from bot import Bot
import llm
import config


class ProductBot(Bot):
    name = "product"
    role = "Product / R&D"
    emoji = "🧭"

    def run(self, ctx):
        r = self._report()
        trending = self._http_get("/api/admin/analytics/trending-files") or {}
        top = trending.get("files", [])[:3]
        r.add_metric("trending_topics", [f.get("subject") for f in top] or ["general"])

        roadmap = llm.reason(
            "You are a product manager for a student study platform.",
            "From this feedback theme — 'students want faster access to exam "
            "notes and dislike download friction' — list 3 roadmap items that "
            "boost engagement. One line each, verb-first.",
            fallback="- Add 'Exam Pack' auto-collection per branch+sem\n"
                     "- One-tap in-app preview (no download) for all files\n"
                     "- Personalized 'continue studying' home rail")
        r.add_insight("Roadmap draft:\n" + roadmap)
        r.add_action("Triage BUGS.md", "Promote HIGH-severity engagement bugs to sprint")
        r.add_recommendation(
            "Instrument feature adoption; kill low-adoption features quarterly.")
        r.save()
        return r
