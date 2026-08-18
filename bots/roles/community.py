"""Community Bot — Community skill.

Researched: word-of-mouth engine, loyalty, UGC, advocates, peer matching.
Uses AbhiHub chat peer-suggestion data where available.
"""
from bot import Bot
import config


class CommunityBot(Bot):
    name = "community"
    role = "Community"
    emoji = "🤝"

    def run(self, ctx):
        r = self._report()
        peers = self._http_get("/api/chat/search-peers", {"q": "__suggested__"}) or {}
        n_peers = len(peers.get("suggested", peers.get("users", [])))
        r.add_metric("suggested_peers_available", n_peers)

        r.add_action("Surface top advocates", "Rank by reputation_score + uploads")
        r.add_action("Nudge peer matching", "Prompt same-college study pairs")
        r.add_insight("Peer matching (same college) increases retention via accountability.")
        r.add_recommendation(
            "Run a monthly 'top contributor' spotlight + credit bonus to fuel UGC.")
        r.save()
        return r
