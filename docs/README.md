# AbhiHub Documentation

Everything here is organised by **purpose**, so you can tell at a glance
whether a document is current truth, a how-to, or a historical record.

| Folder | Contains | Is it current truth? |
|---|---|---|
| [`architecture/`](architecture/) | How the system is built | ✅ Yes — keep updated |
| [`guides/`](guides/) | How to do a specific thing | ✅ Yes — keep updated |
| [`reference/`](reference/) | Generated / exhaustive lookups | ✅ Yes — regenerate on change |
| [`product/`](product/) | Vision, scope, ideas | 🟡 Intent, not implementation |
| [`history/`](history/) | Point-in-time snapshots | ❌ No — never edit, only append |

---

## architecture/ — how it's built

| Document | Read it when |
|---|---|
| [ARCHITECTURE.md](architecture/ARCHITECTURE.md) | **Start here.** Layer map, per-file roles, cross-cutting rules, entry-point hazards. |
| [CSS_PIPELINE.md](architecture/CSS_PIPELINE.md) | Touching styles — which class lives in which file. |

## guides/ — how to do something

| Document | Read it when |
|---|---|
| [USER_GUIDE.md](guides/USER_GUIDE.md) | You want the end-user's view of the product. |
| [GA4_IMPLEMENTATION.md](guides/GA4_IMPLEMENTATION.md) | Working on analytics / event tracking. |
| [FILE_HISTORY_SETUP.md](guides/FILE_HISTORY_SETUP.md) | Working on "previously accessed files". |
| [COMPANY_SKILLS_AND_BOTS.md](guides/COMPANY_SKILLS_AND_BOTS.md) | Running the internal `dev/bots` tooling. |

## reference/ — exhaustive lookups

| Document | Read it when |
|---|---|
| [ROUTES.md](reference/ROUTES.md) | You need the full route map (all 150 rules). |
| [BUGS.md](reference/BUGS.md) | Picking up known issues; has a phased fix plan. |

## product/ — intent

| Document | Read it when |
|---|---|
| [IDEA.md](product/IDEA.md) | You need the original vision and scope. |

## history/ — do not edit

Snapshots kept for context. They describe the state **at the time they
were written** and are deliberately not maintained.

| Document | What it records |
|---|---|
| [REORG_PROGRESS.md](history/REORG_PROGRESS.md) | Step-by-step log of the codebase reorganisation. |
| [audit_report_2026-07-11.md](history/audit_report_2026-07-11.md) | Automated audit, July 2026 (277 findings). |
| [ANALYTICS_CHANGES.md](history/ANALYTICS_CHANGES.md) | Analytics implementation change log. |
| [CSS_CONFLICTS_RESOLVED.md](history/CSS_CONFLICTS_RESOLVED.md) | How CSS conflicts were resolved during the pipeline migration. |

---

## Where things live outside `docs/`

Repository root keeps only the files GitHub surfaces specially:

| File | Why it stays at root |
|---|---|
| [`README.md`](../README.md) | Repo landing page. |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | GitHub links it from PRs and issues. |
| [`SECURITY.md`](../SECURITY.md) | GitHub's security policy tab. |
| [`CHANGELOG.md`](../CHANGELOG.md) | Conventional release history. |
| `LICENSE` | Legal; must be at root. |

Tooling-internal notes live with their tooling and are **not** part of
this tree: `.ai/` (governance rules + audit history), `.know_me/`
(feature specs), `.record/` (task logs), `.documentation/` (subsystem
notes), `.agents/` (agent definitions), `dev/bots/reports/` (bot output).

Two docs stay deliberately co-located with the code they describe:

| File | Documents |
|---|---|
| [`static/css/pipeline/MIGRATION.md`](../static/css/pipeline/MIGRATION.md) | Migrating a page onto the CSS pipeline. |
| [`data/cache/README.md`](../data/cache/README.md) | Store Room cache mechanism. |

---

## Conventions

1. **New doc?** Put it in the folder matching its purpose above. If it
   describes a moment in time, it belongs in `history/`.
2. **Don't edit `history/`.** Add a new dated file instead.
3. **Use relative links** (`../reference/ROUTES.md`) so they survive moves.
4. **Root stays at 4 markdown files.** Anything else goes in `docs/`.
