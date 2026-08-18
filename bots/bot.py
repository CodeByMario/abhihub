"""
Base Bot: every company role inherits from this.

A Bot:
  - has a `name`, `role` (company skill), and `emoji`
  - exposes `run(ctx)` returning a Report dict
  - writes its report to bots/reports/ as JSON + Markdown
  - is safe to run with no network (deterministic fallback logic)

`ctx` is a shared RunContext passed by the orchestrator (CEO bot) so bots can
share data and the final report can be assembled.
"""
import json
import os
from datetime import datetime, timezone

import config


class Report:
    def __init__(self, bot_name: str, role: str, emoji: str):
        self.bot_name = bot_name
        self.role = role
        self.emoji = emoji
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.actions = []        # list of {"action":..., "detail":..., "status":...}
        self.metrics = {}        # key numbers
        self.insights = []       # human readable findings
        self.recommendations = []  # next actions
        self.used_llm = config.has_llm()
        self.used_db = config.has_db()

    def add_action(self, action, detail="", status="done"):
        self.actions.append({"action": action, "detail": detail, "status": status})

    def add_metric(self, key, value):
        self.metrics[key] = value

    def add_insight(self, text):
        self.insights.append(text)

    def add_recommendation(self, text):
        self.recommendations.append(text)

    def to_dict(self):
        return {
            "bot": self.bot_name,
            "role": self.role,
            "emoji": self.emoji,
            "timestamp": self.timestamp,
            "used_llm": self.used_llm,
            "used_db": self.used_db,
            "metrics": self.metrics,
            "actions": self.actions,
            "insights": self.insights,
            "recommendations": self.recommendations,
        }

    def to_markdown(self) -> str:
        out = [f"# {self.emoji} {self.bot_name} — {self.role}",
               f"_Generated {self.timestamp}_",
               "",
               f"- LLM: {'yes' if self.used_llm else 'no (deterministic fallback)'}",
               f"- Live data: {'yes' if self.used_db else 'no (local estimate)'}",
               ""]
        if self.metrics:
            out.append("## Metrics")
            for k, v in self.metrics.items():
                out.append(f"- **{k}**: {v}")
            out.append("")
        if self.actions:
            out.append("## Actions")
            for a in self.actions:
                out.append(f"- [{a['status']}] {a['action']} — {a['detail']}")
            out.append("")
        if self.insights:
            out.append("## Insights")
            for i in self.insights:
                out.append(f"- {i}")
            out.append("")
        if self.recommendations:
            out.append("## Recommendations")
            for r in self.recommendations:
                out.append(f"- {r}")
            out.append("")
        return "\n".join(out)

    def save(self):
        base = os.path.join(config.REPORTS_DIR, self.bot_name)
        with open(base + ".json", "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
        with open(base + ".md", "w", encoding="utf-8") as fh:
            fh.write(self.to_markdown())
        return base


class RunContext:
    """Shared state passed to every bot.run()."""
    def __init__(self):
        self.shared = {}          # bot -> data
        self.reports = {}         # bot -> Report
        self.dry_run = False

    def put(self, key, value):
        self.shared[key] = value

    def get(self, key, default=None):
        return self.shared.get(key, default)


class Bot:
    name = "base"
    role = "base"
    emoji = "🤖"

    def run(self, ctx: RunContext) -> Report:
        raise NotImplementedError

    # --- helpers every bot can use -----------------------------------------
    def _report(self):
        return Report(self.name, self.role, self.emoji)

    @staticmethod
    def _http_get(path: str, params=None):
        """Call an AbhiHub API endpoint if live data is configured."""
        if not config.has_db():
            return None
        import requests
        url = config.API_BASE.rstrip("/") + path
        try:
            resp = requests.get(url, params=params or {}, timeout=15)
            if resp.ok:
                return resp.json()
        except Exception:
            return None
        return None
