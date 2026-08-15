# Documentation Rules

**Status:** Effective Immediately
**Source:** .ai/rules/documentation.md

---

## Documentation Requirements

Every agent that modifies code, routes, or architecture MUST update the
corresponding documentation. The following matrix must be satisfied
before a task can be marked complete:

### When code is modified:

| Change Type                | Required Documentation                |
|----------------------------|---------------------------------------|
| New route added            | `ROUTES.md`                           |
| Route handler modified     | `ROUTES.md` (line reference updated)  |
| New endpoint (API)         | `.documentation/5_apis.md`            |
| API signature changed      | `.documentation/5_apis.md`            |
| Database schema changed    | `migrations/*.sql`, `.documentation/1_database.md` |
| New feature/module         | `.documentation/6_features.md`        |
| Architecture changed       | `.documentation/relation-ship.md`     |
| CSS pipeline changed       | `README.md` (CSS section)             |
| New dependency added       | `requirements.txt` / `package.json`   |

### Documentation Standards:

1. **ROUTES.md** — Maintain a complete, auto-generated route map.
   Each entry must include: route path, method, handler, template,
   dependencies, and line numbers.

2. **CHANGELOG.md** — Append new entries in chronological order.
   Format: `## [version] - YYYY-MM-DD` with `Added/Modified/Removed` sections.

3. **.documentation/*.md** — Technical documentation.
   Update the relevant section document whenever the corresponding
   system changes.

4. **.record/tasks/<AGENT-ID>/** — Task logs.
   Every agent must log its work in its assigned task folder,
   following EP-001 format.

5. **README.md** — User-facing overview. Update when
   setup instructions or feature set changes.

### Before marking a task as complete:

- [ ] Code changes have corresponding documentation updates
- [ ] ROUTES.md is updated for any route changes
- [ ] .documentation/5_apis.md is updated for API changes
- [ ] CHANGELOG.md has a new entry
- [ ] .record/tasks/<AGENT-ID>/ has the daily log entry

### Documentation Agent Responsibilities:

- Monitor for documentation gaps (via `governance audit`)
- Update docs when other agents make code changes
- Maintain the documentation index
- Generate API reference from route analysis
