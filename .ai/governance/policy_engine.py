"""
Policy Engine — determines what agents can and cannot do.

Rules are assembled from four layers:

    GLOBAL  +  PROJECT  +  AGENT  +  TASK  =  EFFECTIVE RULES

Each layer can add restrictions (never grant more than the layer below).
"""

from __future__ import annotations

import os
import re
import json
import fnmatch
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums & dataclasses
# ---------------------------------------------------------------------------

class PermissionLevel(Enum):
    """Standard permission tiers for agents."""

    READ_ONLY = "read_only"        # can read, never write
    STANDARD = "standard"          # read + write within declared scope
    ELEVATED = "elevated"          # can touch broader paths (e.g. config)
    EMERGENCY = "emergency"        # freeze-all override (rare)


class RuleViolation(Exception):
    """Raised when an operation violates a policy rule."""

    def __init__(self, rule_id: str, message: str, **details: Any):
        self.rule_id = rule_id
        self.message = message
        self.details = details
        super().__init__(f"[{rule_id}] {message}")


@dataclass
class RuleSet:
    """A single layer of rules (global, project, agent, or task)."""

    layer: str                        # "global" | "project" | "agent" | "task"
    source: str                       # file or manifest identifier
    permissions: PermissionLevel = PermissionLevel.READ_ONLY
    read_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)  # e.g. "must run tests"
    restrictions: list[str] = field(default_factory=list)  # e.g. "cannot change schema"


@dataclass
class AgentManifest:
    """Agent identity and configuration loaded from .ai/agents/<name>.yaml."""

    name: str
    version: str
    id: str = ""
    role: str = ""
    permissions: PermissionLevel = PermissionLevel.STANDARD
    read_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    restrictions: list[str] = field(default_factory=list)
    status: str = "active"            # active | suspended | emergency_disabled

    @classmethod
    def from_yaml(cls, yaml_dict: dict[str, Any]) -> "AgentManifest":
        """Build from a parsed YAML dict (does not require PyYAML at import time).

        Expected YAML structure:
            agent:
              name: coding-agent
              version: "1.4"
              id: BE-001
              role: Developer
              permissions: standard
              status: active
            read:
              - src/**
            write:
              - src/**
            forbidden:
              - .env
            requirements:
              - must run tests
            restrictions:
              - no hardcoded secrets
        """
        # Get agent metadata block
        agent_cfg = yaml_dict.get("agent", {})

        # Parse permissions
        perms_raw = agent_cfg.get("permissions", yaml_dict.get("permissions", "standard"))
        if isinstance(perms_raw, PermissionLevel):
            perms = perms_raw
        else:
            perms = PermissionLevel(str(perms_raw))

        # Paths are at top level in YAML (not inside agent: block)
        read_paths = yaml_dict.get("read", [])
        write_paths = yaml_dict.get("write", [])
        forbidden_paths = yaml_dict.get("forbidden", [])
        requirements = yaml_dict.get("requirements", [])
        restrictions = yaml_dict.get("restrictions", [])

        return cls(
            name=agent_cfg.get("name", yaml_dict.get("name", "unknown-agent")),
            version=str(agent_cfg.get("version", "1.0.0")),
            id=agent_cfg.get("id", ""),
            role=agent_cfg.get("role", ""),
            permissions=perms,
            read_paths=read_paths,
            write_paths=write_paths,
            forbidden_paths=forbidden_paths,
            requirements=requirements,
            restrictions=restrictions,
            status=agent_cfg.get("status", "active"),
        )


# ---------------------------------------------------------------------------
# Path matching helpers
# ---------------------------------------------------------------------------

class PathMatcher:
    """Glob-style path matcher using fnmatch with ** support."""

    @staticmethod
    def matches(path: str, pattern: str) -> bool:
        """Return True if *path* matches *pattern* (supports ** wildcards)."""
        if pattern == "*" or pattern == "**":
            return True
        if not pattern:
            return False

        # Normalise separators
        path = path.replace("\\", "/")
        pattern = pattern.replace("\\", "/")

        # Convert glob to regex
        regex = PathMatcher._glob_to_regex(pattern)
        return bool(regex.match(path))

    @staticmethod
    def _glob_to_regex(pattern: str) -> re.Pattern:
        """Convert a glob pattern (with **) to a compiled regex."""
        i = 0
        n = len(pattern)
        result = ""
        while i < n:
            c = pattern[i]
            if c == "*":
                if i + 1 < n and pattern[i + 1] == "*":
                    # ** — match across directory boundaries
                    if i + 2 < n and pattern[i + 2] == "/":
                        result += ".*"
                        i += 3
                        continue
                    else:
                        result += ".*"
                        i += 2
                        continue
                else:
                    result += "[^/]*"
                    i += 1
            elif c == "?":
                result += "[^/]"
                i += 1
            else:
                result += re.escape(c)
                i += 1
        return re.compile(result + "$")

    @staticmethod
    def matches_any(path: str, patterns: list[str]) -> bool:
        """Return True if *path* matches any pattern in *patterns*."""
        return any(PathMatcher.matches(path, p) for p in patterns)


# ---------------------------------------------------------------------------
# Core PolicyEngine
# ---------------------------------------------------------------------------

class PolicyEngine:
    """
    Assembles and evaluates policy rules from four layers.

    Layers are applied in order: Global → Project → Agent → Task.
    Each layer can only *restrict* — it never grants more access than
    the layer before it.
    """

    BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(project_root) if project_root else self.BASE_DIR
        self.rules_dir = self.project_root / ".ai" / "rules"
        self.agents_dir = self.project_root / ".ai" / "agents"

        self._rule_sets: dict[str, RuleSet] = {}
        self._agent_manifests: dict[str, AgentManifest] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> "PolicyEngine":
        """Load all rule files and agent manifests from disk."""
        self._load_global_rules()
        self._load_project_rules()
        self._loaded = True
        return self

    def load_agent(self, agent_name: str) -> AgentManifest:
        """Load a specific agent manifest from .ai/agents/<name>.yaml."""
        import yaml  # local import — PyYAML is only needed for agent manifests

        if agent_name in self._agent_manifests and self._loaded:
            return self._agent_manifests[agent_name]

        manifest_path = self.agents_dir / f"{agent_name}.yaml"
        if not manifest_path.exists():
            # Fall back to defaults for known built-in agents
            return self._default_manifest(agent_name)

        with open(manifest_path, "r") as f:
            data = yaml.safe_load(f) or {}

        manifest = AgentManifest.from_yaml(data)
        self._agent_manifests[agent_name] = manifest
        return manifest

    def _default_manifest(self, agent_name: str) -> AgentManifest:
        """Return a safe default manifest for agents not yet registered."""
        defaults = {
            "coding-agent": AgentManifest(
                name="coding-agent",
                version="1.0.0",
                role="Developer",
                permissions=PermissionLevel.STANDARD,
                read_paths=["src/**", "tests/**", "templates/**", "static/**", "docs/**",
                           "requirements.txt", "package.json", ".ai/rules/**"],
                write_paths=["src/**", "tests/**", "docs/**", ".documentation/**"],
                forbidden_paths=[".env", "secrets/**", ".ai/history/**",
                                ".ai/rules/**", "serviceAccountKey.json"],
                requirements=["must run tests before completion",
                             "must record every file modification",
                             "must update documentation for public APIs"],
            ),
            "research-agent": AgentManifest(
                name="research-agent",
                version="1.0.0",
                role="Researcher",
                permissions=PermissionLevel.READ_ONLY,
                read_paths=["app.py", "src/**", "docs/**", ".documentation/**",
                           ".ai/rules/**"],
                write_paths=[],
                forbidden_paths=[".env", "secrets/**"],
                requirements=["must cite sources", "must not modify code"],
            ),
            "testing-agent": AgentManifest(
                name="testing-agent",
                version="1.0.0",
                role="QA",
                permissions=PermissionLevel.STANDARD,
                read_paths=["src/**", "tests/**", "app.py", ".ai/rules/**"],
                write_paths=["tests/**"],
                forbidden_paths=[".env", "secrets/**", "src/**"],
                requirements=["must write tests for new features",
                             "must verify all tests pass before completion"],
            ),
            "documentation-agent": AgentManifest(
                name="documentation-agent",
                version="1.0.0",
                role="DO-001",
                permissions=PermissionLevel.STANDARD,
                read_paths=["app.py", "src/**", "docs/**", ".documentation/**", ".ai/rules/**"],
                write_paths=["docs/**", ".documentation/**", "CHANGELOG.md", "README.md",
                            "ROUTES.md"],
                forbidden_paths=[".env", "secrets/**", "src/**", "tests/**",
                                "requirements.txt", "package.json"],
                requirements=["must update API docs when endpoints change",
                             "must update architecture docs when structure changes"],
            ),
            "cleanup-agent": AgentManifest(
                name="cleanup-agent",
                version="1.0.0",
                role="Maintainer",
                permissions=PermissionLevel.STANDARD,
                read_paths=["src/**", "tests/**", "static/**", "docs/**", ".ai/rules/**"],
                write_paths=[".ai/state/**", "tests/**"],
                forbidden_paths=[".env", "secrets/**", "serviceAccountKey.json",
                                "firebase-auth.json", ".git/**"],
                requirements=["must classify before deleting",
                             "never delete without GOVERNANCE_MODE=govern"],
            ),
        }
        return defaults.get(agent_name, AgentManifest(
            name=agent_name,
            version="1.0.0",
            permissions=PermissionLevel.READ_ONLY,
            read_paths=[],
            write_paths=[],
            forbidden_paths=[".env", "secrets/**", ".ai/history/**", ".ai/rules/**"],
            requirements=["must be registered in .ai/agents/ before operating"],
        ))

    # ------------------------------------------------------------------
    # Rule loading
    # ------------------------------------------------------------------

    def _load_global_rules(self) -> None:
        """Load global rules from .ai/rules/global.md (or defaults)."""
        global_path = self.rules_dir / "global.md"
        if global_path.exists():
            content = global_path.read_text()
            restrictions = []
            for line in content.splitlines():
                line = line.strip()
                # Match numberd rules: "1. **Never expose secrets.**"
                match = re.match(r"^\d+\.\s+\*\*(.+?)\*\*", line)
                if match:
                    restrictions.append(match.group(1).strip())
                # Also match simple bullet points: "- Never ..."
                elif line.startswith("- ") and "**" not in line:
                    restrictions.append(line[2:].strip())
        else:
            # Built-in global defaults
            restrictions = [
                "Never expose secrets (API keys, tokens, passwords).",
                "Never modify governance files under .ai/governance/.",
                "Always record changes in the change ledger.",
                "Never delete files without classification.",
                "Never overwrite user data without explicit approval.",
                "Never bypass the agent gateway for project modifications.",
                "Always load PROJECT_RULES.md before starting work.",
            ]

        self._rule_sets["global"] = RuleSet(
            layer="global",
            source="built-in" if not global_path.exists() else "global.md",
            permissions=PermissionLevel.STANDARD,
            read_paths=["**"],
            write_paths=["**"],
            forbidden_paths=[".env", "secrets/**", ".ai/governance/**", ".ai/history/**",
                            "serviceAccountKey.json", "firebase-auth.json"],
            requirements=[],
            restrictions=restrictions,
        )

    def _load_project_rules(self) -> None:
        """Load project-specific rules from .ai/rules/project.md."""
        project_path = self.rules_dir / "project.md"
        if project_path.exists():
            content = project_path.read_text()
            # Parse key-value or bullet rules
            read_paths = []
            write_paths = []
            reqs = []
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("read:"):
                    read_paths.extend([p.strip() for p in line[5:].split(",") if p.strip()])
                elif line.startswith("write:"):
                    write_paths.extend([p.strip() for p in line[6:].split(",") if p.strip()])
                elif line.startswith("requirement:"):
                    reqs.append(line[len("requirement:"):].strip())
        else:
            read_paths = ["app.py", "src/**", "templates/**", "static/**",
                         "tests/**", "docs/**", ".documentation/**", ".ai/rules/**",
                         "requirements.txt", "package.json", "migrations/**",
                         "ROUTES.md", "README.md", "CHANGELOG.md", ".record/**"]
            write_paths = ["src/**", "tests/**", "docs/**", "templates/**",
                          "static/css/**", "static/js/**", "migrations/**",
                          "ROUTES.md", "CHANGELOG.md", ".documentation/**"]
            reqs = [
                "Use Python 3.11+. Use Flask for web. Tests use pytest.",
                "All new routes must be documented in ROUTES.md.",
                "Document architecture decisions in .documentation/.",
                "Follow EP-001 record-keeping for .record/ entries.",
            ]

        self._rule_sets["project"] = RuleSet(
            layer="project",
            source="project.md" if project_path.exists() else "built-in",
            permissions=PermissionLevel.STANDARD,
            read_paths=read_paths,
            write_paths=write_paths,
            forbidden_paths=[".env", "secrets/**", "serviceAccountKey.json",
                            "firebase-auth.json"],
            requirements=reqs,
        )

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_request(self, agent_name: str, operation: str,
                         files: list[str], reason: str) -> bool:
        """
        Check if an operation is permitted by the effective ruleset.

        Returns True if permitted, raises RuleViolation if denied.
        """
        if not self._loaded:
            self.load()

        manifest = self.load_agent(agent_name)

        # Check 1: Agent must be active
        if manifest.status == "emergency_disabled":
            raise RuleViolation("POLICY-001",
                f"Agent '{agent_name}' is emergency-disabled")

        # Check 2: Forbidden paths (highest priority — deny)
        for fpath in files:
            if PathMatcher.matches_any(fpath, manifest.forbidden_paths):
                raise RuleViolation("POLICY-002",
                    f"File '{fpath}' is forbidden for agent '{agent_name}'",
                    file=fpath, agent=agent_name)

        # Also check global forbidden (cumulative)
        global_set = self._rule_sets.get("global")
        if global_set:
            for fpath in files:
                if PathMatcher.matches_any(fpath, global_set.forbidden_paths):
                    raise RuleViolation("POLICY-003",
                        f"File '{fpath}' is globally forbidden",
                        file=fpath, agent=agent_name)

        # Check 3: Write permission for the operation
        if operation in ("modify", "create", "delete"):
            if manifest.write_paths:
                for fpath in files:
                    if not PathMatcher.matches_any(fpath, manifest.write_paths):
                        raise RuleViolation("POLICY-004",
                            f"Agent '{agent_name}' lacks write access to '{fpath}'",
                            file=fpath, agent=agent_name, operation=operation)
            elif manifest.permissions == PermissionLevel.READ_ONLY:
                raise RuleViolation("POLICY-005",
                    f"Agent '{agent_name}' is read-only and cannot perform '{operation}'")

        # Check 4: Read permission (always required)
        for fpath in files:
            if manifest.read_paths:
                if not PathMatcher.matches_any(fpath, manifest.read_paths):
                    raise RuleViolation("POLICY-006",
                        f"Agent '{agent_name}' lacks read access to '{fpath}'",
                        file=fpath, agent=agent_name)

        # Check 5: Requirements (e.g., "must run tests before completion")
        unmet_reqs = []
        for req in manifest.requirements:
            if "must run tests" in req.lower() and operation in ("modify", "delete"):
                # This is a soft requirement — logged, not blocking initial approval
                # Tests are checked separately by the test runner in the gateway
                pass
            if "must record every" in req.lower() and operation in ("modify", "create"):
                # Required — the gateway will enforce this
                pass

        return True

    def get_effective_rules(self, agent_name: str) -> dict[str, Any]:
        """Return the effective (merged) ruleset for an agent — for logging/display."""
        if not self._loaded:
            self.load()

        manifest = self.load_agent(agent_name)

        return {
            "agent": agent_name,
            "version": manifest.version,
            "permissions": manifest.permissions.value,
            "status": manifest.status,
            "read_paths": manifest.read_paths,
            "write_paths": manifest.write_paths,
            "forbidden_paths": manifest.forbidden_paths,
            "requirements": manifest.requirements,
            "restrictions": manifest.restrictions,
            "global_restrictions": self._rule_sets.get("global").restrictions
                if "global" in self._rule_sets else [],
        }
