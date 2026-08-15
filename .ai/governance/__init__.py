"""
Governance Engine for AbhiHub.

This package implements a multi-agent governance system that sits above
all AI agents and controls what they are allowed to do.

Components:
    - Policy Engine       : determines what agents can/cannot do
    - Change Ledger       : append-only, tamper-evident record of every action
    - Project State       : machine-readable snapshot of project health
    - Agent Gateway       : the ONLY interface sub-agents use to touch the project
    - Governance Engine   : coordinates all components, approval pipeline, modes

CLI:
    python -m ai.governance.cli <command>

Or run directly:
    python .ai/governance/governo.py <command>
"""

from .policy_engine import PolicyEngine, RuleSet, PermissionLevel, RuleViolation
from .change_ledger import ChangeLedger, ChangeRecord, TamperCheckResult
from .project_state import ProjectState, ProjectHealth, ProjectStateManager
from .agent_gateway import AgentGateway, AgentRequest, ApprovalResult, OperationType
from .governance_engine import GovernanceEngine, Mode, AuditReport

__all__ = [
    "PolicyEngine",
    "RuleSet",
    "PermissionLevel",
    "RuleViolation",
    "ChangeLedger",
    "ChangeRecord",
    "TamperCheckResult",
    "ProjectState",
    "ProjectHealth",
    "ProjectStateManager",
    "AgentGateway",
    "AgentRequest",
    "ApprovalResult",
    "OperationType",
    "GovernanceEngine",
    "Mode",
    "AuditReport",
]
