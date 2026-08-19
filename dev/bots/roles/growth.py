"""Growth Bot — Marketing / Growth skill.

Researched responsibilities: SEO, content, social, referral loops, campaign
analytics. Engagement lever: referral loops + content that re-activates users.
"""
from bot import Bot
import llm
import config


class GrowthBot(Bot):
    name = "growth"
    role = "Marketing / Growth"
    emoji = "🚀"

    def run(self, ctx):
        r = self._report()
        r.add_action("Audit canonical/SEO surface", f"BASE_DOMAIN={config.BASE_DOMAIN}")

        canonical_ok = config.BASE_DOMAIN == "abhihub.run.place"
        r.add_metric("canonical_domain", config.BASE_DOMAIN)
        r.add_metric("canonical_consistent", canonical_ok)
        if not canonical_ok:
            r.add_recommendation(
                f"Unify canonical to https://abhihub.run.place (current: {config.BASE_DOMAIN}).")

        # Content ideas — real LLM if key present, else deterministic list.
        prompt_user = (
            "AbhiHub is a study-resource platform for engineering students "
            "(notes, PDFs, practicals). Suggest 5 low-cost growth content ideas "
            "that drive return visits and referrals. Return as a bulleted list, "
            "each under 12 words.")
        ideas = llm.reason(
            "You are a growth marketer for an education SaaS. Be concise.",
            prompt_user,
            fallback=(
                "- Exam-season 'last 7 days' revision packs email\n"
                "- Instagram Reels: '1 note that got a 9-pointer'\n"
                "- Referral: give 50 credits per invited active peer\n"
                "- Branch-wise topper leaderboard (gamified)\n"
                "- WhatsApp channel for new-notes drop alerts"))
        r.add_insight("Content ideas:\n" + ideas)

        r.add_metric("referral_credits_per_invite", 50)
        r.add_action("Queue referral nudge", "Reward invitees who reach 3 views")
        r.add_recommendation(
            "Push the referral + exam-pack campaign 30 days before each semester end.")
        r.save()
        return r
