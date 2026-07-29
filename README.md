# GitHub Automation Bot 🤖

A complete automation system for GitHub repositories that handles **issue triage**, **PR auto-merging**, **feature planning**, and **contributor assignment** — all with zero manual configuration needed after setup.

## Features

| Feature | What It Does |
|---------|-------------|
| **Auto-Triage** | Automatically labels issues with type (bug/enhancement/question), priority (critical/high/medium/low), and component (frontend/backend/mobile/devops/testing) |
| **Auto-Merge** | Merges PRs that pass CI, have approvals, and meet safety checks (no protected files, reasonable size) |
| **Feature Planning** | Breaks down feature ideas into structured sub-task issues with progress tracking |
| **Smart Assignment** | Assigns issues to contributors based on expertise and current workload |
| **Branch Protection** | Configures branch protection rules on your default branch |
| **Issue Templates** | Standardized bug reports, feature requests, and question templates |
| **Dependabot** | Automatic dependency updates with proper labeling |

## Quick Start

### 1. Prerequisites

- A GitHub Personal Access Token (PAT) with `repo`, `workflow`, and `read:org` scopes
- Python 3.8+
- `gh` CLI (optional but recommended)

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run Setup

```bash
python setup.py --repo your-username/your-repo --token $GITHUB_TOKEN
```

This will:
- Create all standardized labels
- Upload issue/PR templates
- Install GitHub Actions workflows
- Configure branch protection
- Set up Dependabot

### 4. Add Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|--------|-------------|
| `OPENROUTER_API_KEY` | For AI-powered feature planning (optional) |

### 5. Done!

The automation is now live. New issues will be auto-triaged, PRs will be auto-merged when ready, and you can plan features with a single command.

## Usage

### Run the Bot Manually

```bash
# Full automation (triage + merge + plan)
python bot.py --repo owner/repo --token $GITHUB_TOKEN --mode all

# Only triage issues
python bot.py --repo owner/repo --token $GITHUB_TOKEN --mode triage

# Only auto-merge PRs
python bot.py --repo owner/repo --token $GITHUB_TOKEN --mode merge

# Plan a specific feature
python bot.py --repo owner/repo --token $GITHUB_TOKEN --mode plan --idea "Add dark mode"

# Plan features from existing feature-request issues
python bot.py --repo owner/repo --token $GITHUB_TOKEN --mode plan
```

### Smart Assignment

```bash
# Assign all unassigned issues
python scripts/auto_assign.py --repo owner/repo --token $GITHUB_TOKEN --all

# Assign a specific issue
python scripts/auto_assign.py --repo owner/repo --token $GITHUB_TOKEN --issue 42
```

### Feature Planning

```bash
# Plan a feature from a text idea
python scripts/feature_planner.py --repo owner/repo --token $GITHUB_TOKEN --idea "Add user authentication"

# Plan features from issues labeled 'feature-request'
python scripts/feature_planner.py --repo owner/repo --token $GITHUB_TOKEN --from-issues
```

### GitHub Actions Workflows

The following workflows run automatically:

1. **Auto-Triage** (`auto-triage.yml`) — Runs on every new issue/PR
2. **Auto-Merge** (`auto-merge.yml`) — Runs on PR events and CI status changes
3. **Feature Planning** (`feature-planning.yml`) — Manually triggered via workflow_dispatch

## How It Works

### Auto-Triage Flow

```
New Issue Created
       ↓
Keyword Analysis (title + body)
       ↓
Type Detection → bug / enhancement / question / documentation
       ↓
Priority Detection → critical / high / medium / low
       ↓
Component Detection → frontend / backend / mobile / devops / testing
       ↓
Labels Applied + Triage Comment Posted
```

### Auto-Merge Safety Checks

Before merging a PR, the bot verifies:

- ✅ Not a draft PR
- ✅ No `do-not-merge` or `wip` labels
- ✅ CI status is `success`
- ✅ All check runs passed
- ✅ At least 1 approved review
- ✅ No changes to protected files (package.json, requirements.txt, etc.)
- ✅ PR size under 500 lines changed
- ✅ Author is not in protected authors list

### Feature Planning Breakdown

The planner uses keyword analysis to match feature ideas to pre-defined task breakdowns:

- **Auth/Login** → 5 sub-tasks (UI, backend, forms, reset, tests)
- **Dark Mode** → 5 sub-tasks (palette, toggle, components, persistence, testing)
- **API** → 5 sub-tasks (spec, endpoints, validation, docs, tests)
- **Dashboard** → 5 sub-tasks (layout, data, UI, charts, tests)
- **Generic** → 5 sub-tasks (research, design, implement, test, document)

## Configuration

### Labels

All labels are defined in `config/labels.json` with names, colors, and descriptions. Customize this file before running setup.

### Contributors

Edit `config/contributors.json` to map contributors to their areas of expertise:

```json
{
  "default": "octocat",
  "frontend": ["frontend-dev", "ui-designer"],
  "backend": ["backend-dev", "api-engineer"]
}
```

### Custom Workflows

You can customize the GitHub Actions workflows in `.github/workflows/`. The workflows use `actions/github-script` so you can modify the JavaScript logic directly.

## Project Structure

```
github-automation-bot/
├── bot.py                          # Main automation bot
├── setup.py                        # One-time repo setup
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── config/
│   ├── labels.json                 # Label definitions
│   └── contributors.json           # Contributor expertise mapping
├── scripts/
│   ├── auto_assign.py              # Smart issue assignment
│   └── feature_planner.py          # Feature breakdown into sub-tasks
└── .github/
    ├── workflows/
    │   ├── auto-triage.yml         # Auto-label issues on creation
    │   ├── auto-merge.yml          # Auto-merge PRs that pass CI
    │   └── feature-planning.yml    # Plan features via workflow_dispatch
    ├── ISSUE_TEMPLATE/
    │   ├── bug_report.md
    │   ├── feature_request.md
    │   ├── question.md
    │   └── config.yml
    ├── PULL_REQUEST_TEMPLATE.md
    └── dependabot.yml
```

## Safety & Best Practices

- **Auto-merge is conservative** — only merges PRs under 500 lines with approvals
- **Protected files** (package.json, requirements.txt, etc.) are never auto-merged
- **Draft PRs** are never auto-merged
- **Branch protection** prevents direct pushes to the default branch
- **All actions are logged** with comments on issues/PRs

## License

MIT
