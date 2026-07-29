Project Recording & Assignment Workflow
=====================================

Purpose:
Every automated or human action that changes the repository or affects
project state must be recorded under `.record/` and follow EP-001 standards.

How AI assistant will operate:
- Work in small, verifiable steps.
- Before each change, create or append a record entry under `.record/`.
- Assign tasks to a specific employee or agent (e.g., `CTO-001`, `backend_team`).
- Update the central todo list and mark progress.

Assignment convention:
- Use `TASK-XXXX` identifiers (incrementing) in `.record/tasks/<ASSIGNEE>/` files.
- Daily logs go to `.record/tasks/<ASSIGNEE>/daily/YYYY-MM-DD.md`.

Reporting:
- After each implementation step, the assistant will append a short summary
  to the task file and to the daily log.
