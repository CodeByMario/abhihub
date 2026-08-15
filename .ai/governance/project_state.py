"""
Project State Manager — maintains a machine-readable snapshot of the
project's current health, structure, and agent status.

State is persisted to `.ai/state/project-state.json` and updated after
every governance cycle.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ProjectHealth:
    """Health metrics for the project."""

    tests: str = "unknown"          # passing | failing | unknown
    test_count: int = 0
    documentation: int = 0          # percentage (0-100)
    organization: int = 0           # percentage (0-100)
    unresolved_changes: int = 0
    last_updated: str = ""


@dataclass
class ProjectState:
    """The complete machine-readable project state."""

    project: dict[str, Any]
    architecture: dict[str, Any]
    agents: dict[str, Any]
    documentation: dict[str, Any]
    health: ProjectHealth
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProjectState":
        health_data = d.get("health", {})
        return cls(
            project=d.get("project", {}),
            architecture=d.get("architecture", {}),
            agents=d.get("agents", {}),
            documentation=d.get("documentation", {}),
            health=ProjectHealth(**health_data),
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# State Manager
# ---------------------------------------------------------------------------

class ProjectStateManager:
    """Loads, analyses, and persists project state."""

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(project_root) if project_root else Path(".")
        self.state_dir = self.project_root / ".ai" / "state"
        self.state_file = self.state_dir / "project-state.json"
        self.codegraph_db = self.project_root / ".codegraph" / "codegraph.db"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_state(self) -> ProjectState | None:
        """Load the last known project state from disk."""
        if not self.state_file.exists():
            return None

        with open(self.state_file, "r") as f:
            data = json.load(f)
        return ProjectState.from_dict(data)

    def scan_and_update(self) -> ProjectState:
        """
        Perform a full scan of the project and update the state file.

        This reads the git status, codegraph DB, test suite, and documentation
        to produce a fresh ProjectState.
        """
        state = self._build_fresh_state()
        self._save_state(state)
        return state

    def get_state(self) -> ProjectState:
        """Get cached state, scanning if necessary."""
        cached = self.load_state()
        if cached is None:
            return self.scan_and_update()

        # Check if stale (older than 1 hour)
        last_updated = cached.health.last_updated
        if last_updated:
            try:
                last_dt = datetime.fromisoformat(last_updated)
                age = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if age > 3600:
                    return self.scan_and_update()
            except (ValueError, TypeError):
                pass  # If parsing fails, just use cached

        return cached

    def update_agent_status(self, agent_name: str, status: str,
                            permissions: str = "standard") -> None:
        """Update or add an agent's status in the project state."""
        state = self.get_state()
        state.agents[agent_name] = {
            "status": status,
            "permissions": permissions,
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }
        self._save_state(state)

    def increment_unresolved(self, delta: int = 1) -> None:
        """Increment the unresolved_changes counter."""
        state = self.get_state()
        state.health.unresolved_changes += delta
        state.health.last_updated = datetime.now(timezone.utc).isoformat()
        self._save_state(state)

    def decrement_unresolved(self, delta: int = 1) -> None:
        """Decrement the unresolved_changes counter (never below 0)."""
        state = self.get_state()
        state.health.unresolved_changes = max(0, state.health.unresolved_changes - delta)
        state.health.last_updated = datetime.now(timezone.utc).isoformat()
        self._save_state(state)

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _build_fresh_state(self) -> ProjectState:
        """Build a fresh ProjectState from live scans."""
        now = datetime.now(timezone.utc).isoformat()
        project_root = self.project_root

        # Git status
        git_status = self._get_git_status()

        # Test status
        test_result = self._run_tests()

        # Codegraph stats
        codegraph_stats = self._get_codegraph_stats()

        # Documentation coverage
        doc_coverage = self._compute_doc_coverage()

        # Organization score
        org_score = self._compute_org_score(git_status)

        # File listing
        files = self._list_project_files()

        state = ProjectState(
            project={
                "name": "AbhiHub",
                "version": self._get_version(),
                "status": "active",
                "branch": git_status.get("branch", "unknown"),
                "dirty": git_status.get("dirty", False),
                "untracked_files": git_status.get("untracked", []),
            },
            architecture={
                "style": "modular_flask",
                "entrypoint": "app.py",
                "language": "python",
                "framework": "flask",
                "database": "supabase_postgresql",
                "key_directories": self._get_key_directories(),
                "file_count": len(files),
                "node_count": codegraph_stats.get("nodes", 0),
                "edge_count": codegraph_stats.get("edges", 0),
                "unresolved_refs": codegraph_stats.get("unresolved", 0),
            },
            agents={
                "coding-agent": {
                    "status": "active",
                    "permissions": "standard",
                    "last_seen": now,
                },
                "research-agent": {
                    "status": "active",
                    "permissions": "read_only",
                    "last_seen": now,
                },
                "testing-agent": {
                    "status": "active",
                    "permissions": "standard",
                    "last_seen": now,
                },
                "documentation-agent": {
                    "status": "active",
                    "permissions": "standard",
                    "last_seen": now,
                },
                "cleanup-agent": {
                    "status": "active",
                    "permissions": "standard",
                    "last_seen": now,
                },
            },
            documentation={
                "architecture": "current" if doc_coverage.get("architecture") else "needs_update",
                "api": "current" if doc_coverage.get("api") else "needs_update",
                "changelog": "current" if doc_coverage.get("changelog") else "needs_update",
                "coverage": doc_coverage.get("percentage", 0),
                "files": doc_coverage.get("files", []),
            },
            health=ProjectHealth(
                tests=test_result.get("status", "unknown"),
                test_count=test_result.get("count", 0),
                documentation=doc_coverage.get("percentage", 0),
                organization=org_score,
                unresolved_changes=len(git_status.get("untracked", [])),
                last_updated=now,
            ),
            metadata={
                "scanner_version": "1.0.0",
                "scan_duration_ms": 0,
                "files_scanned": len(files),
            },
        )

        return state

    def _get_git_status(self) -> dict[str, Any]:
        """Get git branch and dirty status."""
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.project_root, stderr=subprocess.DEVNULL
            ).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            branch = "unknown"

        try:
            status = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=self.project_root, stderr=subprocess.DEVNULL
            ).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            status = ""

        untracked = []
        for line in status.splitlines():
            if line.startswith("??"):
                untracked.append(line[2:].strip())

        return {
            "branch": branch,
            "dirty": bool(status),
            "untracked": untracked,
            "raw": status,
        }

    def _run_tests(self) -> dict[str, Any]:
        """Run the test suite and return results."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "--tb=short", "-q"],
                cwd=self.project_root,
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            # Count passed/failed using regex to handle various formats
            import re
            passed_match = re.search(r"(\d+)\s+passed", output)
            failed_match = re.search(r"(\d+)\s+failed", output)
            passed = int(passed_match.group(1)) if passed_match else 0
            failed = int(failed_match.group(1)) if failed_match else 0
            count = passed + failed
            status = "passing" if result.returncode == 0 and count > 0 else "failing"
            if count == 0 and "no tests ran" in output.lower():
                status = "unknown"
            return {
                "status": status,
                "count": count,
                "passed": passed,
                "failed": failed,
                "return_code": result.returncode,
                "output_tail": output[-500:] if len(output) > 500 else output,
            }
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return {"status": "unknown", "count": 0, "passed": 0, "failed": 0,
                    "return_code": -1}

    def _get_codegraph_stats(self) -> dict[str, int]:
        """Query the codegraph SQLite DB for node/edge counts."""
        import sqlite3

        if not self.codegraph_db.exists():
            return {"nodes": 0, "edges": 0, "unresolved": 0}

        try:
            conn = sqlite3.connect(str(self.codegraph_db))
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM nodes")
            nodes = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM edges")
            edges = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM unresolved_refs")
            unresolved = c.fetchone()[0] if c else 0
            conn.close()
            return {"nodes": nodes, "edges": edges, "unresolved": unresolved}
        except Exception:
            return {"nodes": 0, "edges": 0, "unresolved": 0}

    def _compute_doc_coverage(self) -> dict[str, Any]:
        """Compute documentation coverage percentage."""
        doc_files = {
            "architecture": ".documentation/1_database.md",
            "api": ".documentation/5_apis.md",
            "changelog": "CHANGELOG.md",
        }

        files_present = []
        coverage_count = 0
        total = len(doc_files)

        for key, path in doc_files.items():
            full = self.project_root / path
            if full.exists() and full.stat().st_size > 10:
                files_present.append(path)
                coverage_count += 1

        # Also check README.md and ROUTES.md
        for extra in ["README.md", "ROUTES.md"]:
            full = self.project_root / extra
            if full.exists() and full.stat().st_size > 10:
                files_present.append(extra)
                coverage_count += 1
        total += 2

        percentage = int((coverage_count / total) * 100) if total > 0 else 0

        return {
            "architecture": True if (self.project_root / doc_files["architecture"]).exists() else False,
            "api": True if (self.project_root / doc_files["api"]).exists() else False,
            "changelog": True if (self.project_root / doc_files["changelog"]).exists() else False,
            "percentage": percentage,
            "files": files_present,
        }

    def _compute_org_score(self, git_status: dict) -> int:
        """Compute an organization quality score (0-100)."""
        score = 100

        # Deduct for untracked files
        untracked = git_status.get("untracked", [])
        score -= min(len(untracked) * 2, 20)

        # Deduct for dirty repo
        if git_status.get("dirty"):
            score -= 5

        # Check for common anti-patterns
        project_root = self.project_root
        anti_patterns = ["FINAL_v2_REAL_FINAL.md", "test_final.py", "new_code.py"]
        for pattern in anti_patterns:
            if list(project_root.rglob(pattern)):
                score -= 15

        # Check for duplicate naming
        all_files = [f.name for f in project_root.rglob("*.md") if f.is_file()]
        name_counts = {}
        for name in all_files:
            base = name.replace(".md", "")
            # Check for duplicates like "notes.md", "notes_1.md", "notes_final.md"
            stem = base.split("_")[0]
            name_counts[stem] = name_counts.get(stem, 0) + 1

        for stem, count in name_counts.items():
            if count > 1:
                score -= min(count * 2, 10)

        return max(score, 0)

    def _list_project_files(self) -> list[str]:
        """List all tracked project files (excluding VCS and caches)."""
        files = []
        skip_dirs = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
                     ".codegraph"}
        skip_files = {".DS_Store", "Thumbs.db", "nul"}  # Windows device file
        for root, dirs, filenames in os.walk(self.project_root):
            # Filter out skip dirs in-place
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in filenames:
                if fname.startswith(".") or fname in skip_files:
                    continue
                rel = os.path.relpath(os.path.join(root, fname), self.project_root)
                files.append(rel)
        return files

    def _get_key_directories(self) -> dict[str, str]:
        """Describe the key architectural directories."""
        dirs = {}
        for name, path in [
            ("source", "app.py"),
            ("routes", "ROUTES.md"),
            ("templates", "templates"),
            ("static", "static"),
            ("tests", "tests"),
            ("migrations", "migrations"),
            ("methods", "methods"),
            ("data", "data"),
            ("docs", ".documentation"),
            ("governance", ".ai"),
            ("record", ".record"),
        ]:
            p = self.project_root / path
            dirs[name] = str(p.relative_to(self.project_root)) if p.exists() else ""
        return dirs

    def _get_version(self) -> str:
        """Extract version from git tags or fallback."""
        try:
            version = subprocess.check_output(
                ["git", "describe", "--tags", "--always"],
                cwd=self.project_root, stderr=subprocess.DEVNULL
            ).decode().strip()
            return version
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "0.8.2"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_state(self, state: ProjectState) -> None:
        """Persist the project state to disk."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            f.write(state.to_json())
