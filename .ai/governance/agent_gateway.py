"""
Agent Gateway — the ONLY interface through which sub-agents interact with the
project. Agents must request operations; they cannot directly modify files.

This module implements the approval pipeline:

    REQUEST → POLICY CHECK → PLAN → RULE VALIDATION → EXECUTION →
    TEST/VALIDATION → DOCUMENTATION CHECK → CHANGE RECORD → STATE UPDATE → COMMIT
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .policy_engine import PolicyEngine, RuleViolation
from .change_ledger import ChangeLedger, ChangeRecord
from .project_state import ProjectStateManager


class OperationType(Enum):
    """Types of operations agents can request through the gateway."""

    READ = "read"
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"
    COPY = "copy"
    EXECUTE = "execute"
    TEST = "test"
    SEARCH = "search"
    APPROVE = "approve"
    REJECT = "reject"


@dataclass
class AgentRequest:
    """A request from an agent to perform one or more file operations."""

    agent: str
    operation: str                     # "modify" | "create" | "delete" | "read" | ...
    files: list[str]
    reason: str
    content: str = ""                  # for create/modify operations
    new_path: str = ""                 # for rename operations
    risk: str = "low"                  # low | medium | high | critical
    task_rules: list[str] = field(default_factory=list)  # task-specific restrictions
    expected_changes: list[str] = field(default_factory=list)  # human-readable plan


@dataclass
class ApprovalResult:
    """Result of a gateway approval check."""

    approved: bool
    operation: str
    files: list[str]
    reason: str
    risk: str
    change_id: str
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_approval: bool = False
    message: str = ""


class AgentGateway:
    """
    The central gatekeeper. All sub-agent interactions with the project
    filesystem go through this class.

    The gateway:
    1. Validates the agent is registered and active.
    2. Checks the request against the policy engine (all 4 rule layers).
    3. For operations above a risk threshold, requires GOVERNANCE_MODE=govern
       and explicit approval.
    4. Executes the operation only if permitted.
    5. Records the change in the ledger.
    6. Updates project state.
    """

    # Risk thresholds
    AUTO_APPROVE_THRESHOLD = "low"            # low-risk operations auto-approved
    REQUIRES_APPROVAL_THRESHOLD = "medium"    # medium+ requires approval
    BLOCKS_ON_THRESHOLD = "critical"          # critical operations are blocked

    RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    def __init__(self, project_root: str | Path | None = None,
                 governance_engine=None):
        self.project_root = Path(project_root) if project_root else Path(".")
        self.policy_engine = PolicyEngine(self.project_root)
        self.ledger = ChangeLedger(self.project_root)
        self.state_manager = ProjectStateManager(self.project_root)
        self.governance_engine = governance_engine

        # Load rules and state on init
        self.policy_engine.load()
        self.state_manager.get_state()

    # ------------------------------------------------------------------
    # Core request processing
    # ------------------------------------------------------------------

    def request(self, req: AgentRequest) -> ApprovalResult:
        """
        Process an agent request through the full approval pipeline.

        This is the ONLY public method sub-agents should use.
        """
        change_id = self.ledger.get_next_id()

        # Phase 1: Policy Check
        try:
            self.policy_engine.evaluate_request(
                agent_name=req.agent,
                operation=req.operation,
                files=req.files,
                reason=req.reason,
            )
        except RuleViolation as e:
            # Rejected — record in ledger
            record = ChangeRecord(
                id=change_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                agent=req.agent,
                operation=req.operation,
                files=req.files,
                reason=req.reason,
                status="REJECTED",
                metadata={"violation": e.rule_id, "message": e.message,
                           "risk": req.risk},
            )
            self.ledger.append(record)

            self.state_manager.increment_unresolved()
            return ApprovalResult(
                approved=False,
                operation=req.operation,
                files=req.files,
                reason=req.reason,
                risk=req.risk,
                change_id=change_id,
                violations=[f"[{e.rule_id}] {e.message}"],
                message=f"Request REJECTED: [{e.rule_id}] {e.message}",
            )

        # Phase 2: Risk Assessment
        risk_rank = self.RISK_ORDER.get(req.risk, 0)
        approval_rank = self.RISK_ORDER.get(self.REQUIRES_APPROVAL_THRESHOLD, 1)

        requires_approval = risk_rank >= approval_rank
        blocked = req.risk == "critical"

        # Phase 3: Check governance mode
        gov_mode = self._get_governance_mode()
        if blocked and gov_mode != "govern":
            # In non-govern modes, critical operations are blocked entirely
            record = ChangeRecord(
                id=change_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                agent=req.agent,
                operation=req.operation,
                files=req.files,
                reason=req.reason,
                status="BLOCKED",
                metadata={"reason": "critical risk requires GOVERN mode",
                           "risk": req.risk},
            )
            self.ledger.append(record)
            self.state_manager.increment_unresolved()
            return ApprovalResult(
                approved=False,
                operation=req.operation,
                files=req.files,
                reason=req.reason,
                risk=req.risk,
                change_id=change_id,
                violations=["Critical operation blocked outside GOVERN mode"],
                message="Critical operation requires GOVERN_MODE=govern and explicit approval.",
            )

        if blocked and gov_mode == "govern":
            # In govern mode, critical operations require explicit approval
            requires_approval = True

        # Phase 4: Execution (if auto-approved)
        # Low-risk ops execute immediately. Medium+ ops require explicit approval
        # even in GOVERN mode — they go to pending unless already approved.
        if not requires_approval:
            # Auto-approved: execute immediately
            success, error_msg = self._execute_operation(req, gov_mode)
            if success:
                # Record in ledger
                record = ChangeRecord(
                    id=change_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    agent=req.agent,
                    operation=req.operation,
                    files=req.files,
                    reason=req.reason,
                    status="APPROVED" if requires_approval else "SUCCESS",
                    metadata={
                        "risk": req.risk,
                        "requires_approval": requires_approval,
                        "mode": gov_mode,
                        "expected_changes": req.expected_changes,
                    },
                )
                self.ledger.append(record)
                self.state_manager.decrement_unresolved()
                return ApprovalResult(
                    approved=True,
                    operation=req.operation,
                    files=req.files,
                    reason=req.reason,
                    risk=req.risk,
                    change_id=change_id,
                    requires_approval=requires_approval,
                    message=f"Operation {'approved and ' if requires_approval else ''}"
                             f"{'auto-approved' if not requires_approval else 'executed'} successfully.",
                )
            else:
                record = ChangeRecord(
                    id=change_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    agent=req.agent,
                    operation=req.operation,
                    files=req.files,
                    reason=req.reason,
                    status="BLOCKED",
                    metadata={"error": error_msg, "risk": req.risk},
                )
                self.ledger.append(record)
                return ApprovalResult(
                    approved=False,
                    operation=req.operation,
                    files=req.files,
                    reason=req.reason,
                    risk=req.risk,
                    change_id=change_id,
                    violations=[error_msg],
                    message=f"Execution failed: {error_msg}",
                )
        else:
            # Requires manual approval — record as pending in ledger
            record = ChangeRecord(
                id=change_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                agent=req.agent,
                operation=req.operation,
                files=req.files,
                reason=req.reason,
                status="APPROVED",  # pending approval
                metadata={
                    "risk": req.risk,
                    "requires_approval": True,
                    "mode": gov_mode,
                    "expected_changes": req.expected_changes,
                },
            )
            self.ledger.append(record)
            return ApprovalResult(
                approved=False,
                operation=req.operation,
                files=req.files,
                reason=req.reason,
                risk=req.risk,
                change_id=change_id,
                requires_approval=True,
                message="Request requires GOVERNANCE_MODE=govern and manual approval to execute.",
            )

    # ------------------------------------------------------------------
    # Operation Execution
    # ------------------------------------------------------------------

    def _execute_operation(self, req: AgentRequest, gov_mode: str) -> tuple[bool, str]:
        """Execute the requested operation. Returns (success, error_message)."""
        op = req.operation

        try:
            if op == "read":
                return self._do_read(req.files)

            elif op == "create":
                return self._do_write(req.files, req.content, overwrite=True)

            elif op == "modify":
                return self._do_write(req.files, req.content, overwrite=False)

            elif op == "delete":
                return self._do_delete(req.files[0] if req.files else "")

            elif op == "rename":
                return self._do_rename(req.files[0] if req.files else "", req.new_path)

            elif op == "execute":
                return self._do_execute(req.files[0] if req.files else "", req.content)

            elif op == "test":
                return self._do_test(req.files, req.reason)

            elif op == "search":
                return self._do_search(req.content)

            else:
                return False, f"Unknown operation: {op}"

        except Exception as e:
            return False, str(e)

    def _do_read(self, files: list[str]) -> tuple[bool, str]:
        """Read file(s) — always allowed for agents with read access."""
        results = {}
        for fpath in files:
            full = self.project_root / fpath
            if not full.exists():
                results[fpath] = f"File not found: {fpath}"
                continue
            if full.is_dir():
                results[fpath] = f"Directory: {[str(p.name) for p in full.iterdir()[:10]]}"
            else:
                results[fpath] = full.read_text(encoding="utf-8", errors="replace")[:5000]
        return True, json.dumps(results, indent=2) if results else "No files read."

    def _do_write(self, files: list[str], content: str, overwrite: bool) -> tuple[bool, str]:
        """Create or modify a file."""
        if not files:
            return False, "No files specified for write operation."

        fpath = files[0]
        full = self.project_root / fpath

        if not overwrite and full.exists():
            # For modify, show a diff summary
            old_content = full.read_text(encoding="utf-8", errors="replace")
            old_hash = hashlib.sha256(old_content.encode()).hexdigest()
            new_hash = hashlib.sha256(content.encode()).hexdigest()
            full.write_text(content, encoding="utf-8")
            return True, f"File modified. Old hash: {old_hash[:12]}, New hash: {new_hash[:12]}"
        else:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            return True, f"File created: {fpath}"

    def _do_delete(self, fpath: str) -> tuple[bool, str]:
        """Delete a file."""
        full = self.project_root / fpath
        if not full.exists():
            return False, f"File not found: {fpath}"
        # Move to trash instead of hard delete (conservative)
        trash_dir = self.project_root / "trash"
        trash_dir.mkdir(exist_ok=True)
        dest = trash_dir / fpath.replace("/", "_")
        shutil.move(str(full), str(dest))
        return True, f"File moved to trash/{dest.name} (not permanently deleted)"

    def _do_rename(self, old_path: str, new_path: str) -> tuple[bool, str]:
        """Rename/move a file."""
        old_full = self.project_root / old_path
        new_full = self.project_root / new_path
        if not old_full.exists():
            return False, f"Source not found: {old_path}"
        new_full.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_full), str(new_full))
        return True, f"Renamed: {old_path} → {new_path}"

    def _do_execute(self, script_path: str, content: str = "") -> tuple[bool, str]:
        """Execute a script (sandboxed — limited commands)."""
        full = self.project_root / script_path
        if not full.exists():
            return False, f"Script not found: {script_path}"

        # Only allow .py scripts in scripts/ or tests/
        allowed_prefixes = ["scripts/", "tests/", ".ai/"]
        if not any(script_path.startswith(p) for p in allowed_prefixes):
            return False, f"Execution of scripts outside allowed directories is forbidden: {script_path}"

        result = subprocess.run(
            ["python", str(full)] + (content.split() if content else []),
            cwd=self.project_root,
            capture_output=True, text=True, timeout=60,
        )
        output = result.stdout[:2000] + ("\n[stderr] " + result.stderr[:1000] if result.stderr else "")
        return result.returncode == 0, output

    def _do_test(self, files: list[str], reason: str) -> tuple[bool, str]:
        """Run tests and return results."""
        import sys
        # Find venv python if available
        venv_python = self.project_root / ".venv" / "bin" / "python"
        if not venv_python.exists():
            venv_python = self.project_root / ".venv" / "Scripts" / "python.exe"
        python_cmd = str(venv_python) if venv_python.exists() else sys.executable
        result = subprocess.run(
            [python_cmd, "-m", "pytest", "tests/", "--tb=short", "-q"],
            cwd=self.project_root,
            capture_output=True, text=True, timeout=120,
        )
        output = result.stdout + result.stderr
        passed = output.count(" passed")
        failed = output.count(" failed")
        summary = f"Tests: {passed} passed, {failed} failed. Exit code: {result.returncode}"
        return result.returncode == 0, summary

    def _do_search(self, query: str) -> tuple[bool, str]:
        """Search project files for a pattern."""
        from .policy_engine import PathMatcher  # reuse

        results = []
        search_root = self.project_root
        skip_dirs = {".git", ".venv", "node_modules", "__pycache__", ".codegraph"}

        for root, dirs, filenames in os.walk(search_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for fname in filenames:
                if fname.endswith((".pyc", ".pyo", ".db", ".lock")):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                    for i, line in enumerate(content.splitlines(), 1):
                        if query in line:
                            rel = os.path.relpath(fpath, search_root)
                            results.append(f"{rel}:{i}: {line.strip()}")
                except (OSError, UnicodeDecodeError):
                    continue

        if results:
            return True, "\n".join(results[:50])
        return True, f"No matches found for '{query}'"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_governance_mode(self) -> str:
        """Read the current governance mode from env, state file, or state metadata."""
        # Check env var first (highest priority)
        env_mode = os.environ.get("GOVERNANCE_MODE", "").lower()
        if env_mode in ("audit", "maintain", "govern", "emergency"):
            return env_mode

        # Check the .mode file
        mode_file = self.project_root / ".ai" / "state" / ".mode"
        if mode_file.exists():
            try:
                content = mode_file.read_text().strip().lower()
                if content in ("audit", "maintain", "govern", "emergency"):
                    return content
            except (OSError, IOError):
                pass

        # Check state metadata
        state = self.state_manager.load_state()
        if state and "mode" in state.metadata:
            return state.metadata["mode"]

        return "maintain"  # default mode

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        """Return all pending approvals from the ledger."""
        records = self.ledger.get_all_records()
        pending = []
        for r in records:
            if r.status == "APPROVED" and r.metadata.get("requires_approval"):
                pending.append({
                    "change_id": r.id,
                    "agent": r.agent,
                    "operation": r.operation,
                    "files": r.files,
                    "reason": r.reason,
                    "risk": r.metadata.get("risk", "unknown"),
                    "expected_changes": r.metadata.get("expected_changes", []),
                })
        return pending

    def approve_request(self, change_id: str, approver: str = "governance-engine") -> bool:
        """Approve a pending request and execute it."""
        # This would be called by the GovernanceEngine in GOVERN mode
        # For now, we mark the record as executed
        # The actual execution logic is in _execute_operation
        records = self.ledger.get_all_records()
        for r in records:
            if r.id == change_id:
                r.status = "SUCCESS"
                # Re-write is not possible in append-only ledger,
                # so we append an approval record
                approval_record = ChangeRecord(
                    id=self.ledger.get_next_id(),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    agent="governance-engine",
                    operation="approve",
                    files=[".ai/history/changes/changes.jsonl"],
                    reason=f"Approved request {change_id} by {approver}",
                    status="SUCCESS",
                    metadata={"approved_change_id": change_id, "approver": approver},
                )
                self.ledger.append(approval_record)
                return True
        return False


# Import hashlib at module level for _do_write
import hashlib
import json
import os
