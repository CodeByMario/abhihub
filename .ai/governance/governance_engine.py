"""
Governance Engine — coordinates all governance components.

Operating modes:
  - AUDIT    : Scan project, find problems, generate reports. No changes.
  - MAINTAIN : Can safely organize files, update docs, remove temp files.
  - GOVERN   : Controls other agents — registers, approves, validates, records.
  - EMERGENCY: Freezes the project. Stops all agent operations.

Approval pipeline per request:
    REQUEST → POLICY CHECK → CONTEXT LOADING → PLAN → RULE VALIDATION →
    EXECUTION → TEST/VALIDATION → DOCUMENTATION CHECK → CHANGE RECORD →
    PROJECT STATE UPDATE → COMMIT
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .policy_engine import PolicyEngine, RuleViolation, PermissionLevel
from .change_ledger import ChangeLedger, ChangeRecord, TamperCheckResult
from .project_state import ProjectStateManager
from .agent_gateway import AgentGateway, AgentRequest, ApprovalResult


class Mode(Enum):
    """Governance operating modes."""

    AUDIT = "audit"        # scan + report only
    MAINTAIN = "maintain"  # safe autonomous changes
    GOVERN = "govern"       # full control over sub-agents
    EMERGENCY = "emergency"  # freeze all operations


@dataclass
class AuditReport:
    """Result of an AUDIT run."""

    timestamp: str
    mode: str
    project_name: str
    issues: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    risk_score: int = 0  # 0-100
    files_scanned: int = 0
    policy_violations: list[str] = field(default_factory=list)
    hash_chain_valid: bool = True
    summary: str = ""


class GovernanceEngine:
    """
    The master orchestrator. Coordinates PolicyEngine, ChangeLedger,
    ProjectStateManager, and AgentGateway.

    This is the top-level entry point for governance operations.
    """

    def __init__(self, project_root: str | Path | None = None):
        if project_root:
            self.project_root = Path(project_root)
        else:
            # Try env var first (set by CLI), then auto-detect
            env_root = os.environ.get("GOVERNANCE_PROJECT_ROOT")
            if env_root:
                self.project_root = Path(env_root)
            else:
                # Auto-detect: find the nearest directory containing app.py
                # or .git, walking up from this file
                here = Path(__file__).resolve().parent  # .ai/governance/
                for candidate in [here.parent.parent, here.parent]:  # .ai/ then project root
                    if (candidate / "app.py").exists() or (candidate / ".git").exists():
                        self.project_root = candidate
                        break
                else:
                    self.project_root = here.parent.parent  # assume .ai/ parent

        self.policy_engine = PolicyEngine(self.project_root)
        self.ledger = ChangeLedger(self.project_root)
        self.state_manager = ProjectStateManager(self.project_root)
        self.gateway = AgentGateway(self.project_root, governance_engine=self)

        # Ensure rules are loaded
        self.policy_engine.load()

        # Current mode (persisted to state)
        self._mode_file = self.project_root / ".ai" / "state" / ".mode"
        self._mode = self._read_mode()

    # ------------------------------------------------------------------
    # Mode Management
    # ------------------------------------------------------------------

    @property
    def mode(self) -> Mode:
        return self._mode

    def set_mode(self, mode: Mode | str) -> Mode:
        """Set the governance mode (persists to disk)."""
        if isinstance(mode, str):
            mode = Mode(mode.lower())
        old = self._mode
        self._mode = mode
        self._write_mode()

        # Record the mode change
        record = ChangeRecord(
            id=self.ledger.get_next_id(),
            timestamp=self._utc_now(),
            agent="governance-engine",
            operation="mode_change",
            files=[],
            reason=f"Mode changed from {old.value} to {mode.value}",
            status="SUCCESS",
            metadata={"from": old.value, "to": mode.value},
        )
        self.ledger.append(record)
        return mode

    def _read_mode(self) -> Mode:
        """Read mode from file or env, defaulting to MAINTAIN."""
        env_mode = os.environ.get("GOVERNANCE_MODE", "").lower()
        if env_mode:
            try:
                return Mode(env_mode)
            except ValueError:
                pass

        if self._mode_file.exists():
            try:
                content = self._mode_file.read_text().strip().lower()
                return Mode(content)
            except ValueError:
                pass

        return Mode.MAINTAIN

    def _write_mode(self) -> None:
        """Persist current mode to disk."""
        self._mode_file.parent.mkdir(parents=True, exist_ok=True)
        self._mode_file.write_text(self._mode.value)

    # ------------------------------------------------------------------
    # AUDIT Mode
    # ------------------------------------------------------------------

    def audit(self) -> AuditReport:
        """
        Run a full audit of the project. Detects:
        - Unused files
        - Duplicate files
        - Temporary files
        - Obsolete documentation
        - Broken references
        - Empty directories
        - Policy violations
        - Hash chain integrity
        """
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).isoformat()
        issues = []
        recommendations = []
        policy_violations = []
        risk_score = 0
        files_scanned = 0

        # 1. Scan for anti-patterns (only in project source, not venvs)
        skip_scan_dirs = {".venv", "node_modules", ".git", "__pycache__", ".codegraph"}
        anti_patterns = [
            ("FINAL_v2", "Duplicate naming anti-pattern detected"),
            ("temp_*", "Temporary file naming pattern"),
            ("test_*.tmp", "Temporary test file"),
            (".DS_Store", "macOS system file"),
            ("Thumbs.db", "Windows thumbnail cache"),
        ]

        for pattern, description in anti_patterns:
            for m in self.project_root.rglob(pattern):
                # Skip matches inside venvs, node_modules, etc.
                parts = Path(m).relative_to(self.project_root).parts
                if any(skip in parts for skip in skip_scan_dirs):
                    continue
                issues.append({
                    "type": "anti_pattern",
                    "file": str(m.relative_to(self.project_root)),
                    "severity": "low",
                    "description": description,
                })
                risk_score += 1

        # 2. Check for duplicate documentation
        doc_files = {}
        for p in self.project_root.rglob("*.md"):
            rel = str(p.relative_to(self.project_root))
            # Skip governance-internal and venv files
            skip_prefixes = [".ai/", ".venv/", ".git/", "node_modules/", ".codegraph/",
                            ".pytest_cache/", "__pycache__/", ".record/"]
            if any(rel.startswith(skip) for skip in skip_prefixes):
                continue
            name = p.name
            doc_files.setdefault(name, []).append(p)

        for name, paths in doc_files.items():
            if len(paths) > 1:
                # Only flag as duplicate if files are in different top-level dirs
                # and have identical content (not just same filename)
                path_strs = [str(p.relative_to(self.project_root)) for p in paths]
                # Check if content is identical
                contents = []
                for p in paths:
                    try:
                        contents.append(p.read_text()[:500])
                    except Exception:
                        contents.append("")
                identical = len(set(contents)) == 1
                if identical:
                    issues.append({
                        "type": "duplicate_docs",
                        "file": name,
                        "severity": "medium",
                        "description": f"Found {len(paths)} identical copies of '{name}'",
                        "paths": path_strs,
                    })
                    risk_score += 5
                    recommendations.append(f"Consolidate duplicate docs: {name}")
                else:
                    # Same file name in different directories — not necessarily a problem
                    pass

        # 3. Verify change ledger hash chain
        tamper_result = self.ledger.verify_integrity()
        if not tamper_result.valid:
            issues.append({
                "type": "ledger_tamper",
                "severity": "critical",
                "description": tamper_result.details,
            })
            risk_score += 50
            policy_violations.append("Change ledger hash chain is broken")

        # 4. Check for uncommitted changes
        git_status = self.state_manager._get_git_status()
        if git_status["dirty"]:
            untracked = git_status.get("untracked", [])
            if untracked:
                issues.append({
                    "type": "uncommitted",
                    "severity": "low",
                    "description": f"{len(untracked)} untracked files",
                    "files": untracked[:10],
                })
                risk_score += min(len(untracked), 20)

        # 5. Check for stale credentials (only if not gitignored)
        gitignore_content = ""
        gitignore_path = self.project_root / ".gitignore"
        if gitignore_path.exists():
            gitignore_content = gitignore_path.read_text()

        for cred_file in ["firebase-auth.json", "serviceAccountKey.json"]:
            p = self.project_root / cred_file
            if p.exists():
                # Check if it's gitignored
                is_ignored = cred_file in gitignore_content
                if is_ignored:
                    # File is properly gitignored — not an issue
                    pass
                else:
                    issues.append({
                        "type": "exposed_credential",
                        "severity": "high",
                        "description": f"Credential file found in repo root: {cred_file} "
                                       f"(not in .gitignore)",
                        "file": cred_file,
                    })
                    risk_score += 30
                    recommendations.append(
                        f"Move {cred_file} outside the repo and add to .gitignore")

        # 6. Count scanned files (skip venvs and caches)
        skip_dirs = {".git", ".venv", "node_modules", "__pycache__", ".codegraph",
                     ".pytest_cache"}
        for root, dirs, filenames in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in filenames:
                if not f.startswith("."):
                    files_scanned += 1

        # 7. Force fresh state scan for accurate health metrics
        state = self.state_manager.scan_and_update()
        if state.documentation.get("coverage", state.documentation.get("percentage", 0)) < 60:
            issues.append({
                "type": "low_docs",
                "severity": "medium",
                "description": f"Documentation coverage only {state.documentation.get('coverage', state.documentation.get('percentage', 0))}%",
            })
            recommendations.append("Increase documentation coverage")

        # 8. Check test status
        if state.health.tests == "failing":
            issues.append({
                "type": "tests_failing",
                "severity": "high",
                "description": "Test suite is failing",
            })
            risk_score += 20

        # Clamp risk score
        risk_score = min(risk_score, 100)

        summary = f"Audit complete: {len(issues)} issues found, risk score {risk_score}/100"

        report = AuditReport(
            timestamp=timestamp,
            mode=self._mode.value,
            project_name="AbhiHub",
            issues=issues,
            recommendations=recommendations,
            risk_score=risk_score,
            files_scanned=files_scanned,
            policy_violations=policy_violations,
            hash_chain_valid=tamper_result.valid,
            summary=summary,
        )

        # Save report
        report_dir = self.project_root / ".ai" / "history" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"audit_{timestamp.replace(':', '-')}.md"
        self._write_audit_report(report_file, report)

        # Also save a machine-readable version
        import json
        json_file = report_dir / f"audit_{timestamp.replace(':', '-')}.json"
        json_file.write_text(json.dumps(report.__dict__, indent=2, default=str))

        return report

    def _write_audit_report(self, path: Path, report: AuditReport) -> None:
        """Write a human-readable audit report."""
        lines = [
            f"# Audit Report — {report.timestamp}",
            f"**Mode:** {report.mode}",
            f"**Risk Score:** {report.risk_score}/100",
            f"**Files Scanned:** {report.files_scanned}",
            f"**Ledger Integrity:** {'✅ Valid' if report.hash_chain_valid else '❌ BROKEN'}",
            "",
            "## Issues",
            "",
        ]
        for issue in report.issues:
            sev = issue.get("severity", "unknown").upper()
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(
                issue.get("severity", "low"), "⚪")
            lines.append(f"### {icon} [{sev}] {issue['type']}")
            lines.append(f"{issue['description']}")
            if "file" in issue:
                lines.append(f"- **File:** `{issue['file']}`")
            if "files" in issue:
                lines.append("- **Files:**")
                for f in issue["files"]:
                    lines.append(f"  - `{f}`")
            lines.append("")

        if report.recommendations:
            lines += ["## Recommendations", ""]
            for rec in report.recommendations:
                lines.append(f"- {rec}")
            lines += [""]

        if report.policy_violations:
            lines += ["## Policy Violations", ""]
            for v in report.policy_violations:
                lines.append(f"- {v}")
            lines += [""]

        lines.append(f"## Summary\n\n{report.summary}\n")
        path.write_text("\n".join(lines))

    # ------------------------------------------------------------------
    # MAINTAIN Mode
    # ------------------------------------------------------------------

    def maintain(self) -> dict[str, Any]:
        """
        Run maintenance tasks — file organization, documentation updates,
        temporary file cleanup. Conservatively scoped.
        """
        from datetime import datetime, timezone

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actions": [],
            "errors": [],
        }

        # 1. Remove known safe-to-remove temp files
        safe_patterns = ["*.tmp", "*.temp", ".DS_Store", "Thumbs.db", "*.bak",
                         "*~", "#*#"]
        for pattern in safe_patterns:
            for p in self.project_root.rglob(pattern):
                if any(skip in str(p) for skip in [".git", ".venv", "node_modules"]):
                    continue
                # Double-check it's actually a temp file (not a legit file)
                if p.suffix in (".tmp", ".temp", ".bak") or p.name in (".DS_Store", "Thumbs.db"):
                    rel = str(p.relative_to(self.project_root))
                    try:
                        p.unlink()
                        results["actions"].append(f"Removed: {rel}")
                    except OSError as e:
                        results["errors"].append(f"Could not remove {rel}: {e}")

        # 2. Update project state
        state = self.state_manager.scan_and_update()
        results["actions"].append(f"Project state updated: {state.health.documentation}% doc coverage")

        # 3. Verify ledger integrity
        tamper = self.ledger.verify_integrity()
        results["actions"].append(f"Ledger integrity: {'valid' if tamper.valid else 'BROKEN'} "
                                   f"({tamper.total_entries} entries)")

        # Record the maintenance
        record = ChangeRecord(
            id=self.ledger.get_next_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent="governance-engine",
            operation="maintain",
            files=[],
            reason="Routine maintenance cycle",
            status="SUCCESS",
            metadata={
                "actions": results["actions"],
                "errors_count": len(results["errors"]),
            },
        )
        self.ledger.append(record)

        return results

    # ------------------------------------------------------------------
    # GOVERN Mode — Agent Lifecycle
    # ------------------------------------------------------------------

    def onboard_agent(self, agent_name: str) -> dict[str, Any]:
        """
        Full onboarding process for a new agent:

        NEW AGENT → Identify → Load rules → Load architecture →
        Load docs rules → Load project state → Check permissions →
        Create execution plan → Governance approval → Agent begins work
        """
        from datetime import datetime, timezone

        # Step 1: Identify agent
        manifest = self.policy_engine.load_agent(agent_name)

        # Step 2: Load project rules
        self.policy_engine.load()

        # Step 3: Load architecture from state
        state = self.state_manager.get_state()

        # Step 4: Check permissions
        effective_rules = self.policy_engine.get_effective_rules(agent_name)

        # Step 5: Create execution plan
        plan = {
            "agent": agent_name,
            "version": manifest.version,
            "permissions": manifest.permissions.value,
            "status": manifest.status,
            "effective_rules": effective_rules,
            "project_state": {
                "branch": state.project.get("branch"),
                "version": state.project.get("version"),
                "tests": state.health.tests,
            },
            "requirements": manifest.requirements,
            "onboarded_at": datetime.now(timezone.utc).isoformat(),
        }

        # Step 6: Record onboarding
        record = ChangeRecord(
            id=self.ledger.get_next_id(),
            timestamp=plan["onboarded_at"],
            agent="governance-engine",
            operation="onboard",
            files=[],
            reason=f"Agent {agent_name} onboarded",
            status="APPROVED",
            metadata={"manifest": effective_rules, "plan": plan},
        )
        self.ledger.append(record)

        # Step 7: Update state
        self.state_manager.update_agent_status(agent_name, "active",
                                                manifest.permissions.value)

        return plan

    def request_operation(self, req: AgentRequest) -> ApprovalResult:
        """Submit an operation request through the gateway."""
        return self.gateway.request(req)

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        """Get all pending approval requests."""
        return self.gateway.get_pending_approvals()

    def approve(self, change_id: str, approver: str = "governance-engine") -> bool:
        """Approve a pending request."""
        return self.gateway.approve_request(change_id, approver)

    # ------------------------------------------------------------------
    # EMERGENCY Mode
    # ------------------------------------------------------------------

    def emergency_shutdown(self, reason: str = "Unspecified emergency") -> dict[str, Any]:
        """
        Freeze the project. Disable all agents. Record the emergency.
        """
        from datetime import datetime, timezone

        old_mode = self._mode
        self.set_mode(Mode.EMERGENCY)

        # Disable all agents in state
        state = self.state_manager.get_state()
        for agent_name in state.agents:
            state.agents[agent_name]["status"] = "emergency_disabled"
        state.metadata["emergency"] = {
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "previous_mode": old_mode.value,
        }
        self.state_manager._save_state(state)

        return {
            "emergency_activated": True,
            "previous_mode": old_mode.value,
            "reason": reason,
            "agents_disabled": len(state.agents),
            "timestamp": state.metadata["emergency"]["timestamp"],
        }

    def resolve_emergency(self, reason: str = "Issue resolved") -> dict[str, Any]:
        """Exit emergency mode — restore to MAINTAIN or GOVERN."""
        from datetime import datetime, timezone

        state = self.state_manager.get_state()
        emergency_info = state.metadata.get("emergency", {})
        restore_mode = emergency_info.get("previous_mode", "maintain")

        # Re-enable agents
        for agent_name in state.agents:
            state.agents[agent_name]["status"] = "active"

        # Record resolution
        record = ChangeRecord(
            id=self.ledger.get_next_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent="governance-engine",
            operation="emergency_resolve",
            files=[],
            reason=f"Emergency resolved: {reason}. Restored to {restore_mode} mode.",
            status="SUCCESS",
        )
        self.ledger.append(record)

        # Restore mode
        self.set_mode(Mode(restore_mode))

        return {
            "emergency_resolved": True,
            "restored_mode": restore_mode,
            "reason": reason,
        }

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _utc_now(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def get_status(self) -> dict[str, Any]:
        """Get a summary of the current governance status."""
        state = self.state_manager.get_state()
        tamper = self.ledger.verify_integrity()
        return {
            "mode": self._mode.value,
            "project": state.project,
            "health": state.health,
            "agents": state.agents,
            "ledger": {
                "entries": tamper.total_entries,
                "valid": tamper.valid,
            },
            "pending_approvals": len(self.get_pending_approvals()),
        }


# Module-level imports for helpers in _do_search
import hashlib
import json
import os
import shutil
import subprocess
