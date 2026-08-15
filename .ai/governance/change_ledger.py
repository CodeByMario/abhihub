"""
Change Ledger — append-only, tamper-evident record of every AI action.

Every event is appended to `.ai/history/changes/changes.jsonl` as a JSON line.
Each event includes:
  - id          : sequential (CHG-0001, CHG-0002, ...)
  - timestamp   : ISO-8601 UTC
  - agent       : which agent performed the action
  - operation   : create | modify | delete | test | read | approve | ...
  - files       : list of affected file paths
  - reason      : human-readable explanation
  - status      : SUCCESS | APPROVED | REJECTED | BLOCKED
  - prev_hash   : SHA-256 of the previous entry (tamper-evident chain)
  - hash        : SHA-256 of this entry's canonical content
  - signature   : optional — not implemented (would require key mgmt)

The hash chain makes the log immutable: any modification to a past entry
breaks the chain for all subsequent entries.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ChangeRecord:
    """A single entry in the change ledger."""

    id: str                           # e.g. "CHG-0001"
    timestamp: str                    # ISO-8601 UTC
    agent: str
    operation: str                    # create | modify | delete | test | approve | etc.
    files: list[str]
    reason: str
    status: str = "SUCCESS"           # SUCCESS | APPROVED | REJECTED | BLOCKED
    prev_hash: str = ""               # hash of previous entry
    hash: str = ""                    # hash of this entry
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_canonical_dict(self) -> dict[str, Any]:
        """Return dict in canonical order for hashing (excludes hash & prev_hash)."""
        d = asdict(self)
        # Remove hash and prev_hash from the content we hash
        d.pop("hash", None)
        d.pop("prev_hash", None)
        # Preserve key order for deterministic hashing
        keys = ["id", "timestamp", "agent", "operation", "files",
                "reason", "status", "metadata"]
        return {k: d[k] for k in keys if k in d}

    def compute_hash(self, prev_hash: str) -> str:
        """Compute SHA-256 of this record's canonical content + prev_hash."""
        self.prev_hash = prev_hash
        canonical = json.dumps(self.to_canonical_dict(), sort_keys=False,
                               separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        """Serialize to a JSON line for the ledger file."""
        return json.dumps(asdict(self), separators=(",", ":"), default=str)

    @classmethod
    def from_json(cls, line: str) -> "ChangeRecord":
        """Parse a JSON line back into a ChangeRecord."""
        d = json.loads(line)
        return cls(
            id=d["id"],
            timestamp=d["timestamp"],
            agent=d["agent"],
            operation=d["operation"],
            files=d.get("files", []),
            reason=d.get("reason", ""),
            status=d.get("status", "SUCCESS"),
            prev_hash=d.get("prev_hash", ""),
            hash=d.get("hash", ""),
            metadata=d.get("metadata", {}),
        )


@dataclass
class TamperCheckResult:
    """Result of verifying the integrity of the change ledger."""

    valid: bool
    total_entries: int
    first_broken_index: int | None = None
    broken_id: str | None = None
    expected_hash: str | None = None
    actual_hash: str | None = None
    details: str = ""


# ---------------------------------------------------------------------------
# ChangeLedger
# ---------------------------------------------------------------------------

class ChangeLedger:
    """
    Manages the append-only change log at `.ai/history/changes/changes.jsonl`.

    Also maintains per-agent logs and a human-readable report.
    """

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(project_root) if project_root else Path(".")
        self.changes_dir = self.project_root / ".ai" / "history" / "changes"
        self.ledger_file = self.changes_dir / "changes.jsonl"
        self._counter_file = self.changes_dir / ".counter"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, record: ChangeRecord) -> ChangeRecord:
        """
        Append a change record to the ledger, computing its hash from
        the previous entry's hash. Returns the complete record.
        """
        self.changes_dir.mkdir(parents=True, exist_ok=True)

        prev_hash = self._get_last_hash()
        record.hash = record.compute_hash(prev_hash)

        with open(self.ledger_file, "a") as f:
            f.write(record.to_json() + "\n")

        self._increment_counter()

        # Also write per-agent log
        self._append_agent_log(record)

        return record

    def get_next_id(self) -> str:
        """Return the next sequential change ID (e.g. 'CHG-0007')."""
        counter = self._read_counter()
        return f"CHG-{counter:04d}"

    def get_last_hash(self) -> str:
        """Return the hash of the most recent entry, or empty string if empty."""
        return self._get_last_hash()

    def get_all_records(self) -> list[ChangeRecord]:
        """Read and return all records from the ledger."""
        if not self.ledger_file.exists():
            return []

        records = []
        with open(self.ledger_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(ChangeRecord.from_json(line))
        return records

    def verify_integrity(self) -> TamperCheckResult:
        """
        Verify the hash chain is unbroken.

        Checks:
        1. Each entry's stored hash matches a recomputation of its content.
        2. Each entry's prev_hash matches the previous entry's hash.
        """
        records = self.get_all_records()
        if not records:
            return TamperCheckResult(
                valid=True, total_entries=0,
                details="Ledger is empty — nothing to verify."
            )

        prev_hash = ""
        for i, record in enumerate(records):
            # Verify hash
            expected = record.compute_hash(prev_hash)
            if record.hash != expected:
                return TamperCheckResult(
                    valid=False,
                    total_entries=len(records),
                    first_broken_index=i,
                    broken_id=record.id,
                    expected_hash=expected,
                    actual_hash=record.hash,
                    details=f"Hash mismatch at {record.id}: "
                            f"expected {expected[:16]}..., got {record.hash[:16]}..."
                )

            # Verify prev_hash chain
            if record.prev_hash != prev_hash:
                return TamperCheckResult(
                    valid=False,
                    total_entries=len(records),
                    first_broken_index=i,
                    broken_id=record.id,
                    details=f"Chain break at {record.id}: "
                            f"expected prev_hash={prev_hash[:16]}..., "
                            f"got {record.prev_hash[:16]}..."
                )

            prev_hash = record.hash

        return TamperCheckResult(
            valid=True,
            total_entries=len(records),
            details="All entries verified — hash chain is intact."
        )

    def get_records_by_agent(self, agent: str) -> list[ChangeRecord]:
        """Return all records attributed to a specific agent."""
        return [r for r in self.get_all_records() if r.agent == agent]

    def get_recent(self, n: int = 20) -> list[ChangeRecord]:
        """Return the last *n* records."""
        return self.get_all_records()[-n:]

    def search(self, pattern: str) -> list[ChangeRecord]:
        """Search records by agent, file, operation, or reason (case-insensitive substring)."""
        results = []
        pat = pattern.lower()
        for r in self.get_all_records():
            if (pat in r.agent.lower() or
                pat in r.operation.lower() or
                pat in r.reason.lower() or
                any(pat in f.lower() for f in r.files)):
                results.append(r)
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_last_hash(self) -> str:
        """Read the hash of the last entry without loading all records."""
        if not self.ledger_file.exists():
            return ""

        last_line = ""
        with open(self.ledger_file, "rb") as f:
            # Seek to end and read backwards efficiently
            try:
                f.seek(-2, 2)  # Go to second-to-last byte
                while f.read(1) != b"\n":
                    f.seek(-2, 1)
                last_line = f.readline().decode("utf-8").strip()
            except (OSError, IOError):
                # File too small or empty
                f.seek(0)
                lines = f.readlines()
                if lines:
                    last_line = lines[-1].decode("utf-8").strip()

        if not last_line:
            return ""

        record = ChangeRecord.from_json(last_line)
        return record.hash

    def _read_counter(self) -> int:
        """Read the sequence counter from the counter file."""
        if not self._counter_file.exists():
            return 1
        try:
            return int(self._counter_file.read_text().strip()) + 1
        except (ValueError, IOError):
            return 1

    def _increment_counter(self) -> None:
        """Persist the incremented counter."""
        next_num = self._read_counter()
        self._counter_file.write_text(str(next_num))

    def _append_agent_log(self, record: ChangeRecord) -> None:
        """Append a simplified entry to the agent's personal log."""
        agent_dir = self.changes_dir / record.agent
        agent_dir.mkdir(parents=True, exist_ok=True)
        agent_log = agent_dir / "log.md"

        entry = (
            f"### {record.id}\n\n"
            f"- **Timestamp:** {record.timestamp}\n"
            f"- **Operation:** {record.operation}\n"
            f"- **Files:** {', '.join(record.files) if record.files else '(none)'}\n"
            f"- **Reason:** {record.reason}\n"
            f"- **Status:** {record.status}\n"
            f"- **Hash:** `{record.hash[:16]}...`\n"
            f"\n"
        )

        with open(agent_log, "a") as f:
            f.write(entry)
