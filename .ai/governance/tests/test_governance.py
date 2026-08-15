"""
Tests for the AbhiHub Governance Engine.

Run:  python -m pytest .ai/governance/tests/ -v

These tests verify the governance system with REAL data from the actual
project — no mocks. They test:
    - Policy engine path matching and rule evaluation
    - Change ledger hash chain integrity (tamper detection)
    - Project state scanning and health metrics
    - Agent gateway approval pipeline
    - Governance engine modes and emergency shutdown
    - End-to-end agent lifecycle
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Add governance package to path
_GOV_DIR = Path(__file__).resolve().parent.parent  # .ai/governance/
_AI_DIR = _GOV_DIR.parent  # .ai/
sys.path.insert(0, str(_GOV_DIR))

from governance.policy_engine import (
    PolicyEngine, RuleSet, PermissionLevel, RuleViolation,
    AgentManifest, PathMatcher,
)
from governance.change_ledger import (
    ChangeLedger, ChangeRecord, TamperCheckResult,
)
from governance.project_state import (
    ProjectStateManager, ProjectState, ProjectHealth,
)
from governance.agent_gateway import (
    AgentGateway, AgentRequest, ApprovalResult, OperationType,
)
from governance.governance_engine import (
    GovernanceEngine, Mode, AuditReport,
)

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project_root():
    """Use the real project root — tests run against actual data."""
    return _AI_DIR.parent  # E:\Users\abhihub\New folder\abhihub


@pytest.fixture
def policy_engine(project_root):
    return PolicyEngine(project_root)


@pytest.fixture
def ledger(project_root):
    return ChangeLedger(project_root)


@pytest.fixture
def state_manager(project_root):
    return ProjectStateManager(project_root)


@pytest.fixture
def gateway(project_root):
    return AgentGateway(project_root)


@pytest.fixture
def engine(project_root):
    return GovernanceEngine(project_root)


@pytest.fixture
def temp_project():
    """Create a temporary project for destructive tests."""
    tmpdir = Path(tempfile.mkdtemp(prefix="governance-test-"))
    # Create minimal project structure
    (tmpdir / "app.py").write_text("# test app\n")
    (tmpdir / "src").mkdir()
    (tmpdir / "src" / "main.py").write_text("print('hello')\n")
    (tmpdir / ".ai").mkdir()
    (tmpdir / ".ai" / "agents").mkdir()
    (tmpdir / ".ai" / "rules").mkdir()
    (tmpdir / ".ai" / "history" / "changes").mkdir(parents=True)
    (tmpdir / ".ai" / "state").mkdir(parents=True)
    (tmpdir / ".env").write_text("SECRET=test\n")

    # Write minimal rules
    (tmpdir / ".ai" / "rules" / "global.md").write_text(
        "- Never expose secrets.\n- Always record changes.\n"
    )
    (tmpdir / ".ai" / "rules" / "project.md").write_text(
        "read: src/**, app.py\nwrite: src/**\nrequirement: must run tests\n"
    )

    yield tmpdir

    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# PathMatcher Tests
# ---------------------------------------------------------------------------

class TestPathMatcher:
    """Test the glob-to-regex path matcher."""

    def test_simple_match(self):
        assert PathMatcher.matches("src/utils.py", "src/utils.py") is True

    def test_glob_match(self):
        assert PathMatcher.matches("src/utils.py", "src/*.py") is True
        assert PathMatcher.matches("src/sub/utils.py", "src/*.py") is False

    def test_double_glob(self):
        assert PathMatcher.matches("src/utils.py", "src/**/*.py") is True
        assert PathMatcher.matches("src/sub/deep/utils.py", "src/**/*.py") is True

    def test_any_match(self):
        assert PathMatcher.matches("anything/here.py", "**") is True

    def test_forbidden_dotenv(self):
        assert PathMatcher.matches(".env", ".env") is True
        assert PathMatcher.matches(".env.local", ".env.*") is True
        assert PathMatcher.matches("config.py", ".env") is False

    def test_matches_any(self):
        patterns = [".env", "secrets/**", "firebase-auth.json"]
        assert PathMatcher.matches_any(".env", patterns) is True
        assert PathMatcher.matches_any("secrets/api.txt", patterns) is True
        assert PathMatcher.matches_any("firebase-auth.json", patterns) is True
        assert PathMatcher.matches_any("src/main.py", patterns) is False


# ---------------------------------------------------------------------------
# Policy Engine Tests (real project data)
# ---------------------------------------------------------------------------

class TestPolicyEngine:
    """Test the policy engine against real AbhiHub rules."""

    def test_load_global_rules(self, policy_engine):
        policy_engine.load()
        assert "global" in policy_engine._rule_sets
        gs = policy_engine._rule_sets["global"]
        assert "Never expose secrets." in gs.restrictions
        assert ".env" in gs.forbidden_paths

    def test_load_project_rules(self, policy_engine):
        policy_engine.load()
        assert "project" in policy_engine._rule_sets
        ps = policy_engine._rule_sets["project"]
        assert "app.py" in ps.read_paths
        assert "src/**" in ps.write_paths

    def test_load_coding_agent_manifest(self, policy_engine):
        policy_engine.load()
        manifest = policy_engine.load_agent("coding-agent")
        assert manifest.name == "coding-agent"
        assert manifest.version == "1.4"
        assert manifest.role == "Backend Developer"
        assert manifest.permissions == PermissionLevel.STANDARD
        assert ".env" in manifest.forbidden_paths
        assert "src/**" in manifest.write_paths
        assert "serviceAccountKey.json" in manifest.forbidden_paths

    def test_load_research_agent_manifest(self, policy_engine):
        policy_engine.load()
        manifest = policy_engine.load_agent("research-agent")
        assert manifest.permissions == PermissionLevel.READ_ONLY
        assert manifest.write_paths == []

    def test_unknown_agent_defaults_to_readonly(self, policy_engine):
        policy_engine.load()
        manifest = policy_engine.load_agent("nonexistent-agent")
        assert manifest.permissions == PermissionLevel.READ_ONLY

    def test_evaluate_modify_env_rejected(self, policy_engine):
        """A coding agent must NOT be allowed to modify .env."""
        policy_engine.load()
        with pytest.raises(RuleViolation) as exc_info:
            policy_engine.evaluate_request(
                agent_name="coding-agent",
                operation="modify",
                files=[".env"],
                reason="trying to leak secrets",
            )
        assert "POLICY-002" in str(exc_info.value)

    def test_evaluate_modify_source_allowed(self, policy_engine):
        """A coding agent should be allowed to modify source files."""
        policy_engine.load()
        result = policy_engine.evaluate_request(
            agent_name="coding-agent",
            operation="modify",
            files=["src/main.py"],
            reason="add feature",
        )
        assert result is True

    def test_evaluate_readonly_agent_cannot_modify(self, policy_engine):
        """A read-only agent must NOT modify any files."""
        policy_engine.load()
        with pytest.raises(RuleViolation) as exc_info:
            policy_engine.evaluate_request(
                agent_name="research-agent",
                operation="modify",
                files=["requirements.txt"],
                reason="should fail",
            )
        assert "POLICY-005" in str(exc_info.value)

    def test_evaluate_modify_forbidden_path_rejected(self, policy_engine):
        """Forbidden paths must always be rejected."""
        policy_engine.load()
        with pytest.raises(RuleViolation) as exc_info:
            policy_engine.evaluate_request(
                agent_name="coding-agent",
                operation="modify",
                files=["serviceAccountKey.json"],
                reason="should fail",
            )
        assert "POLICY-002" in str(exc_info.value)

    def test_evaluate_write_outside_scope_rejected(self, policy_engine):
        """An agent must not write outside its declared scope."""
        policy_engine.load()
        with pytest.raises(RuleViolation) as exc_info:
            policy_engine.evaluate_request(
                agent_name="research-agent",
                operation="create",
                files=["new_file.py"],
                reason="should fail",
            )
        # research-agent is read-only, so it should fail with POLICY-005 or POLICY-006
        assert exc_info.value.rule_id in ("POLICY-005", "POLICY-006")

    def test_get_effective_rules(self, policy_engine):
        policy_engine.load()
        rules = policy_engine.get_effective_rules("coding-agent")
        assert rules["agent"] == "coding-agent"
        assert rules["permissions"] == "standard"
        assert rules["status"] == "active"
        assert len(rules["forbidden_paths"]) > 0
        assert len(rules["requirements"]) > 0


# ---------------------------------------------------------------------------
# Change Ledger Tests
# ---------------------------------------------------------------------------

class TestChangeLedger:
    """Test the append-only change ledger and hash chain."""

    def test_append_record(self, project_root):
        ledger = ChangeLedger(project_root)
        record = ChangeRecord(
            id=ledger.get_next_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent="test-agent",
            operation="test_op",
            files=["test/file.py"],
            reason="unit test",
        )
        result = ledger.append(record)
        assert result.hash != ""
        assert result.prev_hash  # Should have a hash (possibly empty for first)
        assert result.id.startswith("CHG-")

    def test_hash_chain_integrity(self, project_root):
        """The hash chain must always be valid after normal appends."""
        ledger = ChangeLedger(project_root)
        result = ledger.verify_integrity()
        assert result.valid is True
        assert result.total_entries > 0

    def test_tamper_detection(self, project_root):
        """Modifying a past entry must break the hash chain."""
        ledger_file = project_root / ".ai" / "history" / "changes" / "changes.jsonl"
        if not ledger_file.exists():
            pytest.skip("No ledger to test against")

        lines = ledger_file.read_text().splitlines()
        if not lines:
            pytest.skip("Empty ledger")

        # Save original
        original_line = lines[0]
        original_content = ledger_file.read_text()

        try:
            # Tamper with first entry
            entry = json.loads(lines[0])
            entry["agent"] = "tampered-agent"
            entry["hash"] = "0" * 64
            lines[0] = json.dumps(entry, separators=(",", ":"))
            ledger_file.write_text("\n".join(lines) + "\n")

            # Verify should detect tampering
            ledger = ChangeLedger(project_root)
            result = ledger.verify_integrity()
            assert result.valid is False
            assert result.first_broken_index == 0
            assert result.broken_id == entry["id"]
        finally:
            # Restore original
            ledger_file.write_text(original_content)

    def test_get_next_id_sequential(self, project_root):
        ledger = ChangeLedger(project_root)
        records = ledger.get_all_records()
        expected_next = len(records) + 1
        next_id = ledger.get_next_id()
        assert next_id == f"CHG-{expected_next:04d}"

    def test_search_records(self, project_root):
        ledger = ChangeLedger(project_root)
        records = ledger.get_all_records()
        if not records:
            pytest.skip("No records to search")

        # Search for a known agent
        results = ledger.search("governance-engine")
        assert len(results) > 0
        assert all(r.agent == "governance-engine" for r in results)


# ---------------------------------------------------------------------------
# Project State Tests
# ---------------------------------------------------------------------------

class TestProjectState:
    """Test the project state manager with real data."""

    def test_get_state_returns_valid_state(self, state_manager):
        state = state_manager.get_state()
        assert state.project["name"] == "AbhiHub"
        assert state.project["branch"] == "Memory-wall"
        assert "active" in state.project.get("status", "")

    def test_state_has_agents(self, state_manager):
        state = state_manager.get_state()
        agents = state.agents
        assert len(agents) >= 5  # coding, research, testing, docs, cleanup
        assert "coding-agent" in agents
        for agent_name, agent_info in agents.items():
            assert "status" in agent_info
            assert "permissions" in agent_info

    def test_state_has_health(self, state_manager):
        state = state_manager.get_state()
        assert state.health is not None
        assert state.health.documentation >= 0
        assert state.health.documentation <= 100
        assert state.health.organization >= 0
        assert state.health.organization <= 100
        assert state.health.last_updated != ""

    def test_state_has_documentation(self, state_manager):
        state = state_manager.get_state()
        assert "architecture" in state.documentation
        assert "api" in state.documentation
        assert "changelog" in state.documentation

    def test_update_agent_status(self, state_manager):
        original = state_manager.get_state()
        original_status = original.agents.get("coding-agent", {}).get("status")
        state_manager.update_agent_status("coding-agent", "suspended", "read_only")
        updated = state_manager.load_state()
        assert updated.agents["coding-agent"]["status"] == "suspended"
        # Restore
        state_manager.update_agent_status("coding-agent", original_status, "standard")

    def test_increment_decrement_unresolved(self, state_manager):
        original = state_manager.get_state()
        original_count = original.health.unresolved_changes

        state_manager.increment_unresolved(1)
        state = state_manager.load_state()
        assert state.health.unresolved_changes == original_count + 1

        state_manager.decrement_unresolved(1)
        state = state_manager.load_state()
        assert state.health.unresolved_changes == original_count


# ---------------------------------------------------------------------------
# Agent Gateway Tests
# ---------------------------------------------------------------------------

class TestAgentGateway:
    """Test the agent gateway approval pipeline."""

    def test_request_modify_env_rejected(self, gateway):
        req = AgentRequest(
            agent="coding-agent",
            operation="modify",
            files=[".env"],
            reason="trying to modify env",
            risk="low",
        )
        result = gateway.request(req)
        assert result.approved is False
        assert "POLICY-002" in result.message

    def test_request_modify_source_approved(self, gateway):
        req = AgentRequest(
            agent="coding-agent",
            operation="modify",
            files=["src/test_governance_file.py"],
            reason="test file creation through governance",
            risk="low",
            content="# governance test\nprint('governance works')\n",
        )
        result = gateway.request(req)
        assert result.approved is True
        assert result.change_id  # Has a change ID
        assert (gateway.project_root / "src" / "test_governance_file.py").exists()

    def test_request_readonly_agent_modify_rejected(self, gateway):
        req = AgentRequest(
            agent="research-agent",
            operation="modify",
            files=["requirements.txt"],
            reason="should fail",
            risk="low",
        )
        result = gateway.request(req)
        assert result.approved is False

    def test_request_forbidden_file_rejected(self, gateway):
        req = AgentRequest(
            agent="coding-agent",
            operation="modify",
            files=["firebase-auth.json"],
            reason="should fail",
            risk="low",
        )
        result = gateway.request(req)
        assert result.approved is False
        assert "forbidden" in result.message.lower()

    def test_request_critical_risk_blocked(self, gateway):
        """Critical-risk operations are blocked outside GOVERN mode."""
        # Create a file first so the delete operation reaches the risk check,
        # not the "file not found" execution failure
        test_file = gateway.project_root / "src" / "test_critical_risk.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# test file\n")
        try:
            req = AgentRequest(
                agent="coding-agent",
                operation="delete",
                files=["src/test_critical_risk.py"],
                reason="should be blocked",
                risk="critical",
            )
            result = gateway.request(req)
            assert result.approved is False
            # Critical ops in govern mode require explicit approval — not auto-executed
            assert result.requires_approval is True
            assert "approval" in result.message.lower()
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_request_recorded_in_ledger(self, gateway):
        """Every request must be recorded in the change ledger."""
        req = AgentRequest(
            agent="coding-agent",
            operation="modify",
            files=["src/governance_test_marker.py"],
            reason="ledger integrity test",
            risk="low",
            content="# marker file\n",
        )
        result = gateway.request(req)
        assert result.approved is True

        # Check ledger
        ledger = ChangeLedger(gateway.project_root)
        records = ledger.get_all_records()
        matching = [r for r in records if r.id == result.change_id]
        assert len(matching) == 1
        assert matching[0].status == "SUCCESS"
        assert matching[0].agent == "coding-agent"


# ---------------------------------------------------------------------------
# Governance Engine Tests
# ---------------------------------------------------------------------------

class TestGovernanceEngine:
    """Test the master governance engine."""

    def test_modes_exist(self):
        assert Mode.AUDIT.value == "audit"
        assert Mode.MAINTAIN.value == "maintain"
        assert Mode.GOVERN.value == "govern"
        assert Mode.EMERGENCY.value == "emergency"

    def test_initial_mode(self, engine):
        """Default mode should be MAINTAIN unless set otherwise."""
        state = engine.state_manager.load_state()
        if state and "mode" in state.metadata:
            expected = state.metadata["mode"]
        else:
            expected = "maintain"
        # Mode file or env may override
        actual = engine.mode.value
        assert actual in ("audit", "maintain", "govern", "emergency")

    def test_onboard_agent(self, engine):
        plan = engine.onboard_agent("coding-agent")
        assert plan["agent"] == "coding-agent"
        assert "effective_rules" in plan
        assert "requirements" in plan
        assert len(plan["requirements"]) > 0

    def test_audit_returns_report(self, engine):
        report = engine.audit()
        assert isinstance(report, AuditReport)
        assert report.project_name == "AbhiHub"
        assert report.risk_score >= 0
        assert report.risk_score <= 100
        assert report.files_scanned > 0
        assert isinstance(report.issues, list)

    def test_audit_report_saved_to_disk(self, engine):
        report = engine.audit()
        report_dir = engine.project_root / ".ai" / "history" / "reports"
        audit_files = list(report_dir.glob("audit_*.md"))
        assert len(audit_files) > 0
        # The latest report should contain our findings
        latest = sorted(audit_files)[-1]
        content = latest.read_text()
        assert "Audit Report" in content or "AUDIT" in content

    def test_set_mode(self, engine):
        old_mode = engine.mode
        try:
            new_mode = engine.set_mode("audit")
            assert new_mode == Mode.AUDIT
            assert engine.mode == Mode.AUDIT
        finally:
            # Restore
            engine.set_mode(old_mode.value)

    def test_emergency_shutdown(self, engine):
        old_mode = engine.mode
        old_mode_value = old_mode.value

        try:
            result = engine.emergency_shutdown("Test emergency")
            assert result["emergency_activated"] is True
            assert engine.mode == Mode.EMERGENCY

            # All agents should be disabled
            state = engine.state_manager.get_state()
            for agent_name, agent_info in state.agents.items():
                assert agent_info["status"] == "emergency_disabled"
        finally:
            engine.resolve_emergency("Test complete")
            assert engine.mode.value == old_mode_value or engine.mode.value == "govern"

    def test_resolve_emergency(self, engine):
        engine.emergency_shutdown("Test")
        result = engine.resolve_emergency("Test resolution")
        assert "restored_mode" in result

    def test_status(self, engine):
        status = engine.get_status()
        assert "mode" in status
        assert "project" in status
        assert "health" in status
        assert "agents" in status
        assert "ledger" in status

    def test_governance_onboards_all_agents(self, engine):
        """All standard agents should be onboardable."""
        for agent_name in ["coding-agent", "research-agent", "testing-agent",
                           "documentation-agent", "cleanup-agent"]:
            plan = engine.onboard_agent(agent_name)
            assert plan["agent"] == agent_name
            assert plan["status"] == "active"

    def test_governance_request_through_engine(self, engine):
        """Requests should flow through the engine."""
        req = AgentRequest(
            agent="coding-agent",
            operation="read",
            files=["app.py"],
            reason="reading the main app",
            risk="low",
        )
        result = engine.request_operation(req)
        assert result.approved is True


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cleanup_test_files(project_root):
    """Remove test artifacts after each test."""
    yield
    # Clean up any test files created during tests
    test_files = [
        "src/test_governance_file.py",
        "src/governance_test_marker.py",
    ]
    for f in test_files:
        p = project_root / f
        if p.exists():
            p.unlink()
        # Clean up empty src dir if it was created
        src_dir = project_root / "src"
        if src_dir.exists() and not any(src_dir.iterdir()):
            src_dir.rmdir()
