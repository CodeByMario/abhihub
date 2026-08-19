"""
CLI runner for the AbhiHub autonomous company bots.

Usage:
  python dev/bots/run.py --list              # list all bots + roles
  python dev/bots/run.py --dry-run           # run all bots, no network (deterministic)
  python dev/bots/run.py --bot engagement    # run a single role bot
  python dev/bots/run.py --cycle             # full company cycle via CEO bot
"""
import argparse
import importlib
import os
import sys

# Make `dev/bots/` importable + add repo root so config can find .env.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # dev/bots -> dev -> repo root
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from bot import RunContext  # noqa: E402
import config  # noqa: E402

# Ensure --dry-run truly disables all network access.
if "--dry-run" in sys.argv:
    config.DRY_RUN = True

from roles.ceo import CeoBot, ROSTER  # noqa: E402
from roles.growth import GrowthBot  # noqa: E402
from roles.engagement import EngagementBot  # noqa: E402
from roles.revenue import RevenueBot  # noqa: E402
from roles.ops import OpsBot  # noqa: E402
from roles.finance import FinanceBot  # noqa: E402
from roles.product import ProductBot  # noqa: E402
from roles.community import CommunityBot  # noqa: E402

BY_NAME = {
    "growth": GrowthBot, "engagement": EngagementBot, "revenue": RevenueBot,
    "ops": OpsBot, "finance": FinanceBot, "product": ProductBot,
    "community": CommunityBot, "ceo": CeoBot,
}


def list_bots():
    print("AbhiHub Company Bots — roster\n")
    for name, cls in BY_NAME.items():
        inst = cls()
        print(f"  {inst.emoji} {name:10s} -> {inst.role}")
    print("\nRun: python dev/bots/run.py --dry-run | --bot <name> | --cycle")


def main():
    ap = argparse.ArgumentParser(description="AbhiHub autonomous company bots")
    ap.add_argument("--list", action="store_true", help="list bots")
    ap.add_argument("--dry-run", action="store_true",
                    help="run all role bots with no network (deterministic)")
    ap.add_argument("--bot", help="run a single bot by name")
    ap.add_argument("--cycle", action="store_true",
                    help="full company cycle via CEO bot")
    args = ap.parse_args()

    if args.list:
        list_bots()
        return

    ctx = RunContext()
    ctx.dry_run = bool(args.dry_run)

    if args.bot:
        name = args.bot.lower()
        if name not in BY_NAME:
            print(f"Unknown bot '{args.bot}'. Use --list.")
            sys.exit(1)
        rep = BY_NAME[name]().run(ctx)
        print(f"{rep.emoji} {rep.bot_name}: {len(rep.actions)} actions, "
              f"{len(rep.recommendations)} recommendations")
        print(f"   report -> dev/bots/reports/{rep.bot_name}.md")
        return

    # Default / --dry-run / --cycle all run the CEO cycle (runs everyone).
    ceo = CeoBot()
    rep = ceo.run(ctx)
    print(f"\n{rep.emoji} CEO cycle complete — {rep.metrics.get('bots_run')} bots ran.")
    for rec in rep.recommendations:
        print("  - " + rec)
    print(f"\nConsolidated report -> dev/bots/reports/company_consolidated.json")


if __name__ == "__main__":
    main()
