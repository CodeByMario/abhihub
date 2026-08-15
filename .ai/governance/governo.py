#!/usr/bin/env python
"""
Governo — CLI for the AbhiHub Governance Engine.

Usage:
    governo audit           # Run AUDIT mode: scan, report problems
    governo maintain        # Run MAINTAIN mode: safe auto-fixes
    governo status          # Show current governance status
    governo onboard <agent> # Onboard a new agent
    governo mode <mode>     # Set governance mode (audit|maintain|govern|emergency)
    governo verify          # Verify change ledger integrity
    governo rules <agent>   # Show effective rules for an agent
    governo agents          # List all registered agents
    governo approve <id>    # Approve a pending request
    governo log <agent>     # Show change log for an agent
    governo emergency <reason>  # Activate emergency shutdown
    governo resolve <reason>    # Resolve emergency mode

Examples:
    governo audit
    governo mode govern
    governo onboard coding-agent
    governo rules coding-agent
    governo approve CHG-0042
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running both as a module (python -m ai.governance.governo)
# and as a script (python .ai/governance/governo.py)
if __package__:
    # Running as part of the governance package
    from .governance_engine import GovernanceEngine, Mode
    from .agent_gateway import AgentRequest, OperationType
    from .change_ledger import ChangeRecord
else:
    # Running as a standalone script — fix sys.path
    _this_dir = Path(__file__).resolve().parent
    if str(_this_dir.parent) not in sys.path:
        sys.path.insert(0, str(_this_dir.parent))
    os.environ.setdefault("GOVERNANCE_PROJECT_ROOT", str(_this_dir.parent.parent))
    from governance.governance_engine import GovernanceEngine, Mode
    from governance.agent_gateway import AgentRequest, OperationType
    from governance.change_ledger import ChangeRecord


def main():
    """Entry point for the governo CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="governo",
        description="AbhiHub Governance Engine — AI agent governance CLI",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # audit
    sub.add_parser("audit", help="Run AUDIT mode: scan project, report problems")

    # maintain
    sub.add_parser("maintain", help="Run MAINTAIN mode: safe auto-fixes")

    # status
    sub.add_parser("status", help="Show current governance status")

    # onboard
    p_onboard = sub.add_parser("onboard", help="Onboard a new agent")
    p_onboard.add_argument("agent", help="Agent name (e.g. coding-agent)")

    # mode
    p_mode = sub.add_parser("mode", help="Set governance mode")
    p_mode.add_argument("mode", choices=["audit", "maintain", "govern", "emergency"],
                        help="New operating mode")

    # verify
    sub.add_parser("verify", help="Verify change ledger integrity")

    # rules
    p_rules = sub.add_parser("rules", help="Show effective rules for an agent")
    p_rules.add_argument("agent", help="Agent name")

    # agents
    sub.add_parser("agents", help="List all registered agents")

    # approve
    p_approve = sub.add_parser("approve", help="Approve a pending request")
    p_approve.add_argument("change_id", help="Change ID to approve (e.g. CHG-0042)")

    # log
    p_log = sub.add_parser("log", help="Show change log")
    p_log.add_argument("agent", nargs="?", default="all",
                       help="Agent name (default: all)")
    p_log.add_argument("--json", action="store_true", help="Output as JSON")

    # emergency
    p_emergency = sub.add_parser("emergency", help="Activate emergency shutdown")
    p_emergency.add_argument("reason", help="Reason for emergency shutdown")

    # resolve
    p_resolve = sub.add_parser("resolve", help="Resolve emergency mode")
    p_resolve.add_argument("reason", nargs="?", default="Issue resolved",
                           help="Resolution reason")

    # request (for sub-agents to use the gateway)
    p_req = sub.add_parser("request", help="Submit an operation request via gateway")
    p_req.add_argument("agent", help="Agent name")
    p_req.add_argument("operation", choices=["read", "create", "modify", "delete",
                                              "rename", "execute", "test", "search"],
                        help="Operation type")
    p_req.add_argument("file", help="Target file path")
    p_req.add_argument("--reason", default="Agent request", help="Reason for operation")
    p_req.add_argument("--content", default="", help="Content for create/modify")
    p_req.add_argument("--risk", default="low", choices=["low", "medium", "high", "critical"],
                        help="Risk level")
    p_req.add_argument("--new-path", default="", help="New path (for rename)")

    # plan (show onboarding plan for an agent)
    p_plan = sub.add_parser("plan", help="Show onboarding plan for an agent")
    p_plan.add_argument("agent", help="Agent name")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    engine = GovernanceEngine()

    if args.command == "audit":
        report = engine.audit()
        _print_audit_report(report, engine)

    elif args.command == "maintain":
        results = engine.maintain()
        print(f"Maintenance complete: {len(results['actions'])} actions, "
              f"{len(results['errors'])} errors")
        for action in results["actions"]:
            print(f"  ✓ {action}")
        for err in results["errors"]:
            print(f"  ✗ {err}")

    elif args.command == "status":
        status = engine.get_status()
        print(json.dumps(status, indent=2, default=str))

    elif args.command == "onboard":
        plan = engine.onboard_agent(args.agent)
        effective = plan.get("effective_rules", {})
        print(f"✅ Agent '{args.agent}' onboarded successfully")
        print(f"  Version:      {plan.get('version', '?')}")
        print(f"  Permissions:  {plan.get('permissions', '?')}")
        print(f"  Status:       {plan.get('status', '?')}")
        reqs = plan.get("requirements", [])
        print(f"  Requirements ({len(reqs)}):")
        for r in reqs:
            print(f"    • {r}")

    elif args.command == "mode":
        old_mode = engine.mode.value
        engine.set_mode(args.mode)
        print(f"Mode changed: {old_mode} → {args.mode}")

    elif args.command == "verify":
        result = engine.ledger.verify_integrity()
        status = "✅ VALID" if result.valid else "❌ BROKEN"
        print(f"Change Ledger Integrity: {status}")
        print(f"  Total entries: {result.total_entries}")
        if not result.valid:
            print(f"  First broken: {result.broken_id} (index {result.first_broken_index})")
            print(f"  Details: {result.details}")

    elif args.command == "rules":
        rules = engine.policy_engine.get_effective_rules(args.agent)
        print(json.dumps(rules, indent=2, default=str))

    elif args.command == "agents":
        agents_dir = engine.project_root / ".ai" / "agents"
        agents = sorted([f.stem for f in agents_dir.glob("*.yaml")])
        print("Registered agents:")
        for a in agents:
            manifest = engine.policy_engine.load_agent(a)
            print(f"  {a:30s}  role={manifest.role:20s}  perms={manifest.permissions.value:10s}  status={manifest.status}")

    elif args.command == "approve":
        success = engine.approve(args.change_id)
        if success:
            print(f"Approved: {args.change_id}")
        else:
            print(f"Not found: {args.change_id}")

    elif args.command == "log":
        if args.agent == "all":
            records = engine.ledger.get_all_records()
        else:
            records = engine.ledger.get_records_by_agent(args.agent)

        if args.json:
            data = [r.__dict__ for r in records]
            print(json.dumps(data, indent=2, default=str))
        else:
            print(f"Change Log ({len(records)} entries)")
            print("=" * 80)
            for r in records:
                print(f"  {r.id} [{r.status:7s}] {r.operation:12s} by {r.agent:25s} "
                      f"{r.timestamp[:19]} UTC")
                if r.files:
                    for f in r.files:
                        print(f"           file: {f}")
                print(f"           reason: {r.reason[:80]}")
                print()

    elif args.command == "emergency":
        result = engine.emergency_shutdown(args.reason)
        print(f"🚨 EMERGENCY MODE ACTIVATED")
        print(f"  Reason: {args.reason}")
        print(f"  Previous mode: {result['previous_mode']}")
        print(f"  Agents disabled: {result['agents_disabled']}")
        print(f"  Timestamp: {result['timestamp']}")

    elif args.command == "resolve":
        result = engine.resolve_emergency(args.reason)
        print(f"✅ Emergency resolved: {args.reason}")
        print(f"  Restored mode: {result['restored_mode']}")

    elif args.command == "request":
        req = AgentRequest(
            agent=args.agent,
            operation=args.operation,
            files=[args.file],
            reason=args.reason,
            content=args.content,
            risk=args.risk,
            new_path=args.new_path,
        )
        result = engine.request_operation(req)
        print(f"Operation: {result.operation} on {', '.join(result.files)}")
        print(f"Status: {'Approved' if result.approved else 'Rejected'}")
        print(f"Risk: {result.risk}")
        print(f"Change ID: {result.change_id}")
        if result.violations:
            print(f"Violations: {result.violations}")
        if result.warnings:
            print(f"Warnings: {result.warnings}")
        print(f"Message: {result.message}")

    elif args.command == "plan":
        plan = engine.onboard_agent(args.agent)
        print(f"=== Onboarding Plan for {args.agent} ===\n")
        print(f"Version: {plan['version']}")
        print(f"Role: {plan.get('role', 'N/A')}")
        print(f"Permissions: {plan['permissions']}")
        print(f"Status: {plan['status']}")
        print(f"\nEffective Rules:")
        print(f"  Read paths:     {', '.join(plan['effective_rules']['read_paths'])}")
        print(f"  Write paths:    {', '.join(plan['effective_rules']['write_paths'])}")
        print(f"  Forbidden:      {', '.join(plan['effective_rules']['forbidden_paths'])}")
        print(f"\nRequirements:")
        for r in plan["requirements"]:
            print(f"  • {r}")
        if plan["restrictions"]:
            print(f"\nRestrictions:")
            for r in plan["restrictions"]:
                print(f"  • {r}")

    return 0


def _print_audit_report(report, engine):
    """Pretty-print an audit report to stdout."""
    print(f"\n{'=' * 60}")
    print(f"  AUDIT REPORT — {report.project_name}")
    print(f"  Timestamp: {report.timestamp}")
    print(f"  Mode: {report.mode}")
    print(f"  {'=' * 60}")
    print(f"  Risk Score: {report.risk_score}/100")
    print(f"  Files Scanned: {report.files_scanned}")
    print(f"  Ledger Integrity: {'✅ Valid' if report.hash_chain_valid else '❌ BROKEN'}")
    print(f"\n  Issues Found: {len(report.issues)}")
    print("-" * 60)

    for issue in report.issues:
        sev = issue.get("severity", "unknown").upper()
        icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(
            issue.get("severity", "low"), "⚪")
        print(f"  {icon} [{sev}] {issue['type']}: {issue['description']}")
        if "file" in issue:
            print(f"      File: {issue['file']}")

    if report.recommendations:
        print(f"\n  Recommendations ({len(report.recommendations)}):")
        for rec in report.recommendations:
            print(f"  • {rec}")

    if report.policy_violations:
        print(f"\n  Policy Violations:")
        for v in report.policy_violations:
            print(f"  ✗ {v}")

    print(f"\n  Summary: {report.summary}")

    # Show where full report was saved
    report_dir = engine.project_root / ".ai" / "history" / "reports"
    latest = sorted(report_dir.glob("audit_*.md"))[-1] if report_dir.exists() else None
    if latest:
        print(f"\n  Full report saved to: {latest.relative_to(engine.project_root)}")
    print()


if __name__ == "__main__":
    sys.exit(main())
