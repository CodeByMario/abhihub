# Global Rules — Apply to Every Agent

**Status:** Effective Immediately
**Source:** .ai/rules/global.md

---

## Core Principles

1. **Never expose secrets.** API keys, tokens, passwords, and credentials
   must never be written to logs, code, or any file in the repository.

2. **Never modify governance files.** Files under `.ai/governance/` are
   read-only to all agents. Only the Governance Engine itself can modify
   these.

3. **Always record changes.** Every meaningful action must be appended to
   the change ledger at `.ai/history/changes/changes.jsonl`.

4. **Never delete files without classification.** Before removing any file,
   it must be classified as SAFE_TO_REMOVE. The cleanup-agent is the only
   exception, and only in GOVERN mode.

5. **Never overwrite user data.** User-generated content (documents, profiles,
   memory walls) must be preserved. Only system files may be modified.

6. **Never bypass the agent gateway.** All file modifications must go through
   the AgentGateway. Direct filesystem manipulation is a policy violation.

7. **Always load project rules before starting work.** Every agent must read
   `.ai/rules/project.md` and `.ai/rules/documentation.md` before beginning
   any task.

8. **Never commit credentials.** Credential files (`.env`, `serviceAccountKey.json`,
   `firebase-auth.json`) must never be staged or committed.

9. **Maintain a tamper-evident chain.** The change ledger's hash chain must
   always be valid. If integrity fails, the issue must be reported immediately.

10. **Respect the audit trail.** Records under `.record/` must be appended to,
    never rewritten. Mark entries as superseded, not deleted.

---

## Emergency Procedures

If you discover a critical issue:

1. Do NOT attempt to fix it directly.
2. Report it to the Governance Engine via `emergency_shutdown()`.
3. Wait for the mode to be restored by a human operator.
