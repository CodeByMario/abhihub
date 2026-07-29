#!/usr/bin/env python3
"""
GitHub Automation Bot — Full Repo Management
=============================================
Automatically manages your GitHub repo by:
  1. Triage issues (auto-label, auto-assign, prioritize)
  2. Auto-merge PRs that pass CI (with safety checks)
  3. Plan new features (break down into tasks, create issues)
  4. Keep the repo clean and contributor-friendly

Usage:
  python bot.py --repo owner/repo --token $GITHUB_TOKEN --mode triage
  python bot.py --repo owner/repo --token $GITHUB_TOKEN --mode merge
  python bot.py --repo owner/repo --token $GITHUB_TOKEN --mode plan --idea "Add dark mode"
  python bot.py --repo owner/repo --token $GITHUB_TOKEN --mode all
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ─── Configuration ───────────────────────────────────────────────────────────

CONFIG_DIR = Path(__file__).parent / "config"

# Load label definitions
with open(CONFIG_DIR / "labels.json") as f:
    LABELS = json.load(f)

# Load contributor roster (for smart assignment)
CONTRIBUTORS_FILE = CONFIG_DIR / "contributors.json"
if CONTRIBUTORS_FILE.exists():
    with open(CONTRIBUTORS_FILE) as f:
        CONTRIBUTORS = json.load(f)
else:
    CONTRIBUTORS = {}

# ─── GitHub API Client ───────────────────────────────────────────────────────


class GitHubAPI:
    """Thin wrapper around the GitHub REST API."""

    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo
        self.base = f"https://api.github.com/repos/{repo}"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{self.base}{path}"
        resp = requests.get(url, headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict) -> dict:
        url = f"{self.base}{path}"
        resp = requests.post(url, headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, data: dict) -> dict:
        url = f"{self.base}{path}"
        resp = requests.patch(url, headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, data: dict) -> dict:
        url = f"{self.base}{path}"
        resp = requests.put(url, headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    # ─── Issues ───

    def list_issues(self, state: str = "open", labels: str = None,
                    assignee: str = None, **kwargs) -> list:
        params = {"state": state, "per_page": 100}
        if labels:
            params["labels"] = labels
        if assignee:
            params["assignee"] = assignee
        params.update(kwargs)
        issues = []
        page = 1
        while True:
            params["page"] = page
            resp = self._get("/issues", params=params)
            page_issues = [i for i in resp if "pull_request" not in i]
            if not page_issues:
                break
            issues.extend(page_issues)
            page += 1
        return issues

    def get_issue(self, number: int) -> dict:
        return self._get(f"/issues/{number}")

    def create_issue(self, title: str, body: str, labels: list = None,
                     assignees: list = None, milestone: int = None) -> dict:
        data = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        if assignees:
            data["assignees"] = assignees
        if milestone:
            data["milestone"] = milestone
        return self._post("/issues", data)

    def add_labels(self, number: int, labels: list) -> dict:
        return self._post(f"/issues/{number}/labels", {"labels": labels})

    def add_assignees(self, number: int, assignees: list) -> dict:
        return self._post(f"/issues/{number}/assignees", {"assignees": assignees})

    def add_comment(self, number: int, body: str) -> dict:
        return self._post(f"/issues/{number}/comments", {"body": body})

    def update_issue(self, number: int, **kwargs) -> dict:
        return self._patch(f"/issues/{number}", kwargs)

    # ─── Pull Requests ───

    def get_pr(self, number: int) -> dict:
        return self._get(f"/pulls/{number}")

    def list_prs(self, state: str = "open", **kwargs) -> list:
        params = {"state": state, "per_page": 100}
        params.update(kwargs)
        prs = []
        page = 1
        while True:
            params["page"] = page
            resp = self._get("/pulls", params=params)
            if not resp:
                break
            prs.extend(resp)
            page += 1
        return prs

    def get_pr_files(self, number: int) -> list:
        return self._get(f"/pulls/{number}/files")

    def get_pr_reviews(self, number: int) -> list:
        return self._get(f"/pulls/{number}/reviews")

    def merge_pr(self, number: int, commit_title: str = None,
                 commit_message: str = None, sha: str = None) -> dict:
        data = {"merge_method": "squash"}
        if commit_title:
            data["commit_title"] = commit_title
        if commit_message:
            data["commit_message"] = commit_message
        if sha:
            data["sha"] = sha
        return self._put(f"/pulls/{number}/merge", data)

    def enable_auto_merge(self, number: int) -> dict:
        """Enable GitHub's native auto-merge (requires repo setting)."""
        pr = self.get_pr(number)
        # Use GraphQL for auto-merge
        query = """
        mutation($input: EnablePullRequestAutoMergeInput!) {
          enablePullRequestAutoMerge(input: $input) {
            clientMutationId
          }
        }
        """
        resp = requests.post(
            "https://api.github.com/graphql",
            headers={**self.headers, "Accept": "application/vnd.github+json"},
            json={"query": query, "variables": {
                "input": {"pullRequestId": pr["node_id"], "mergeMethod": "SQUASH"}
            }},
        )
        resp.raise_for_status()
        return resp.json()

    def get_pr_status(self, number: int) -> dict:
        """Get combined CI status for a PR."""
        pr = self.get_pr(number)
        sha = pr["head"]["sha"]
        return self._get(f"/commits/{sha}/status")

    def get_pr_check_runs(self, number: int) -> list:
        pr = self.get_pr(number)
        sha = pr["head"]["sha"]
        resp = self._get(f"/commits/{sha}/check-runs")
        return resp.get("check_runs", [])

    # ─── Labels & Milestones ───

    def list_labels(self) -> list:
        return self._get("/labels", {"per_page": 100})

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return self._post("/labels", {
            "name": name, "color": color, "description": description
        })

    def list_milestones(self, state: str = "all") -> list:
        return self._get("/milestones", {"state": state, "per_page": 100})

    def create_milestone(self, title: str, due_date: str = None,
                         description: str = "") -> dict:
        data = {"title": title}
        if due_date:
            data["due_on"] = due_date
        if description:
            data["description"] = description
        return self._post("/milestones", data)

    # ─── Repo Info ───

    def get_repo(self) -> dict:
        return self._get("")

    def get_contributors(self) -> list:
        return self._get("/contributors", {"per_page": 100})

    def get_collaborators(self) -> list:
        return self._get("/collaborators", {"per_page": 100})


# ─── Triage Engine ───────────────────────────────────────────────────────────


class TriageEngine:
    """Automatically triages GitHub issues."""

    def __init__(self, api: GitHubAPI):
        self.api = api

    def triage_issue(self, issue: dict) -> dict:
        """Apply labels, assign, and prioritize a single issue."""
        actions = []
        number = issue["number"]
        title = issue.get("title", "")
        body = issue.get("body") or ""

        # Skip if already has labels
        existing_labels = {l["name"] for l in issue.get("labels", [])}

        # ─── Label Detection ───
        labels_to_add = []

        # Type detection
        type_label = self._detect_type(title, body)
        if type_label and type_label not in existing_labels:
            labels_to_add.append(type_label)

        # Priority detection
        priority_label = self._detect_priority(title, body)
        if priority_label and priority_label not in existing_labels:
            labels_to_add.append(priority_label)

        # Component detection
        component_labels = self._detect_components(title, body)
        for cl in component_labels:
            if cl not in existing_labels:
                labels_to_add.append(cl)

        if labels_to_add:
            self.api.add_labels(number, labels_to_add)
            actions.append(f"Added labels: {', '.join(labels_to_add)}")

        # ─── Auto-Assignment ───
        assignee = self._suggest_assignee(title, body, component_labels)
        if assignee:
            # Check if already assigned
            current_assignees = {a["login"] for a in issue.get("assignees", [])}
            if assignee not in current_assignees:
                self.api.add_assignees(number, [assignee])
                actions.append(f"Assigned to @{assignee}")

        # ─── Add needs-triage label if no type detected ───
        if not type_label and "needs-triage" not in existing_labels:
            self.api.add_labels(number, ["needs-triage"])
            actions.append("Added label: needs-triage")

        # ─── Comment with triage summary ───
        if actions:
            comment = (
                f"## 🤖 Auto-Triage Report\n\n"
                f"This issue has been automatically triaged:\n\n"
                + "\n".join(f"- {a}" for a in actions)
                + f"\n\n*Triaged by GitHub Automation Bot at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*"
            )
            self.api.add_comment(number, comment)

        return {"issue": number, "actions": actions}

    def _detect_type(self, title: str, body: str) -> str:
        text = (title + " " + body).lower()
        if any(w in text for w in ["bug", "fix", "broken", "error", "crash",
                                    "doesn't work", "not working", "fail"]):
            return "bug"
        if any(w in text for w in ["feature", "request", "add", "new feature",
                                    "enhancement", "improve", "wishlist"]):
            return "enhancement"
        if any(w in text for w in ["question", "how to", "help", "support",
                                    "confused", "unclear"]):
            return "question"
        if any(w in text for w in ["doc", "documentation", "readme", "example"]):
            return "documentation"
        return None

    def _detect_priority(self, title: str, body: str) -> str:
        text = (title + " " + body).lower()
        if any(w in text for w in ["critical", "urgent", "security", "emergency",
                                    "crash", "data loss", "p0"]):
            return "priority:critical"
        if any(w in text for w in ["high", "important", "broken", "p1"]):
            return "priority:high"
        if any(w in text for w in ["medium", "moderate", "p2"]):
            return "priority:medium"
        if any(w in text for w in ["low", "minor", "p3", "nice to have"]):
            return "priority:low"
        return "priority:medium"  # default

    def _detect_components(self, title: str, body: str) -> list:
        text = (title + " " + body).lower()
        components = []
        # Define component keywords
        component_keywords = {
            "frontend": ["ui", "ux", "css", "html", "react", "vue", "angular",
                         "frontend", "frontend", "button", "page", "layout"],
            "backend": ["api", "server", "database", "db", "sql", "backend",
                        "endpoint", "server", "express", "django", "flask"],
            "mobile": ["mobile", "ios", "android", "app", "react native",
                       "flutter", "swift", "kotlin"],
            "devops": ["ci", "cd", "deploy", "docker", "kubernetes", "k8s",
                       "terraform", "aws", "azure", "gcp", "pipeline"],
            "testing": ["test", "testing", "unit test", "integration test",
                        "e2e", "cypress", "jest", "pytest"],
        }
        for component, keywords in component_keywords.items():
            if any(kw in text for kw in keywords):
                components.append(component)
        return components

    def _suggest_assignee(self, title: str, body: str, components: list) -> str:
        """Suggest an assignee based on component expertise."""
        if not CONTRIBUTORS:
            return None

        # Try component-based assignment
        for component in components:
            if component in CONTRIBUTORS:
                return CONTRIBUTORS[component]

        # Try keyword-based assignment
        text = (title + " " + body).lower()
        for person, keywords in CONTRIBUTORS.items():
            if isinstance(keywords, list):
                if any(kw in text for kw in keywords):
                    return person

        # Fallback: round-robin or first contributor
        return CONTRIBUTORS.get("default")

    def run(self, limit: int = 20) -> list:
        """Triage all open issues that need attention."""
        issues = self.api.list_issues(state="open", labels="needs-triage",
                                     per_page=limit)
        # Also get issues with no labels
        all_issues = self.api.list_issues(state="open", per_page=limit)
        unlabeled = [i for i in all_issues if not i.get("labels")]
        issues = list({i["number"]: i for i in issues + unlabeled}.values())

        results = []
        for issue in issues:
            result = self.triage_issue(issue)
            results.append(result)
            print(f"  ✅ Triaged #{issue['number']}: {issue['title'][:60]}...")

        return results


# ─── Auto-Merge Engine ───────────────────────────────────────────────────────


class AutoMergeEngine:
    """Automatically merges PRs that pass all checks."""

    # Files/patterns that should NOT be auto-merged
    PROTECTED_PATHS = [
        "package.json", "package-lock.json", "requirements.txt",
        "Pipfile", "Pipfile.lock", "Cargo.toml", "Cargo.lock",
        "go.mod", "go.sum", "pom.xml", "build.gradle",
    ]

    # Authors who should NOT be auto-merged
    PROTECTED_AUTHORS = []

    def __init__(self, api: GitHubAPI):
        self.api = api

    def should_auto_merge(self, pr: dict) -> tuple:
        """Check if a PR is safe to auto-merge. Returns (bool, reason)."""
        number = pr["number"]

        # ─── Check 1: Draft PR ───
        if pr.get("draft"):
            return False, "PR is a draft"

        # ─── Check 2: Author trust ───
        author = pr["user"]["login"]
        if author in self.PROTECTED_AUTHORS:
            return False, f"Author @{author} is in protected authors list"

        # ─── Check 3: Required labels ───
        labels = {l["name"] for l in pr.get("labels", [])}
        if "do-not-merge" in labels or "wip" in labels:
            return False, "PR has 'do-not-merge' or 'wip' label"

        # ─── Check 4: Changes to protected files ───
        files = self.api.get_pr_files(number)
        changed_files = [f["filename"] for f in files]
        for protected in self.PROTECTED_PATHS:
            if protected in changed_files:
                return False, f"Changes to protected file: {protected}"

        # ─── Check 5: CI status ───
        status = self.api.get_pr_status(number)
        if status["state"] != "success":
            return False, f"CI status is '{status['state']}', not 'success'"

        # ─── Check 6: Check runs ───
        check_runs = self.api.get_pr_check_runs(number)
        for run in check_runs:
            if run.get("conclusion") not in ("success", "neutral", "skipped"):
                return False, f"Check '{run['name']}' has conclusion '{run.get('conclusion')}'"

        # ─── Check 7: Required reviews ───
        reviews = self.api.get_pr_reviews(number)
        approved = any(r["state"] == "APPROVED" for r in reviews)
        if not approved:
            return False, "No approved reviews"

        # ─── Check 8: No unresolved comments ───
        # (GitHub API doesn't easily expose this, skip for now)

        # ─── Check 9: Small enough PR ───
        total_changes = sum(f.get("additions", 0) + f.get("deletions", 0)
                           for f in files)
        if total_changes > 500:
            return False, f"PR too large ({total_changes} lines changed)"

        return True, "All checks passed"

    def merge_pr(self, pr: dict) -> dict:
        """Merge a PR with a descriptive commit message."""
        number = pr["number"]
        title = pr["title"]
        body = pr.get("body") or ""

        # Build commit message
        commit_title = f"{title} (#{number})"
        commit_message = f"Auto-merged by GitHub Automation Bot\n\n{body}"

        try:
            result = self.api.merge_pr(number, commit_title, commit_message)
            return {"success": True, "pr": number, "result": result}
        except requests.HTTPError as e:
            return {"success": False, "pr": number, "error": str(e)}

    def run(self, limit: int = 10) -> list:
        """Check all open PRs for auto-merge eligibility."""
        prs = self.api.list_prs(state="open", per_page=limit)
        results = []

        for pr in prs:
            should_merge, reason = self.should_auto_merge(pr)
            if should_merge:
                print(f"  ✅ Merging PR #{pr['number']}: {pr['title'][:60]}...")
                result = self.merge_pr(pr)
                results.append(result)
            else:
                print(f"  ⏭️  Skipping PR #{pr['number']}: {reason}")
                results.append({"pr": pr["number"], "skipped": True, "reason": reason})

        return results


# ─── Feature Planning Engine ─────────────────────────────────────────────────


class FeaturePlanner:
    """Breaks down feature ideas into structured, actionable issues."""

    def __init__(self, api: GitHubAPI):
        self.api = api

    def plan_feature(self, idea: str) -> list:
        """Break a feature idea into sub-tasks and create issues."""
        # Use a simple heuristic to break down the feature
        tasks = self._break_down(idea)

        # Create a parent tracking issue
        parent = self.api.create_issue(
            title=f"🚀 Feature: {idea}",
            body=self._feature_template(idea, tasks),
            labels=["enhancement", "feature", "priority:medium"],
        )
        print(f"  ✅ Created parent issue #{parent['number']}")

        # Create sub-task issues
        sub_issues = []
        for i, task in enumerate(tasks, 1):
            sub = self.api.create_issue(
                title=f"[{i}/{len(tasks)}] {task['title']}",
                body=f"Part of #{parent['number']} — {task['description']}",
                labels=["task", f"part:{i}"],
            )
            sub_issues.append(sub)
            print(f"  ✅ Created sub-task #{sub['number']}: {task['title'][:50]}...")

        # Link sub-tasks to parent
        for sub in sub_issues:
            self.api.add_comment(parent["number"],
                                f"Sub-task: #{sub['number']} — {sub['title']}")

        return {"parent": parent, "sub_tasks": sub_issues}

    def _break_down(self, idea: str) -> list:
        """Break a feature idea into sub-tasks using keyword analysis."""
        idea_lower = idea.lower()

        # Generic breakdown based on common patterns
        if any(w in idea_lower for w in ["login", "auth", "sign in", "register"]):
            return [
                {"title": "Design auth UI mockups",
                 "description": "Create wireframes for login, register, and password reset screens."},
                {"title": "Implement backend auth endpoints",
                 "description": "Create API endpoints for login, register, logout, and token refresh."},
                {"title": "Add frontend auth forms",
                 "description": "Build login and registration forms with validation."},
                {"title": "Set up password reset flow",
                 "description": "Implement email-based password reset with secure tokens."},
                {"title": "Add auth tests",
                 "description": "Write unit and integration tests for all auth flows."},
            ]

        if any(w in idea_lower for w in ["dark mode", "theme", "color scheme"]):
            return [
                {"title": "Design dark theme color palette",
                 "description": "Define all color tokens for the dark theme."},
                {"title": "Add theme toggle component",
                 "description": "Create a switch component to toggle between light/dark themes."},
                {"title": "Apply dark theme to all components",
                 "description": "Update all UI components to support dark mode."},
                {"title": "Persist theme preference",
                 "description": "Save user's theme preference in localStorage/cookies."},
                {"title": "Test dark mode across browsers",
                 "description": "Verify dark mode works in Chrome, Firefox, Safari, Edge."},
            ]

        if any(w in idea_lower for w in ["api", "endpoint", "rest", "graphql"]):
            return [
                {"title": "Design API specification",
                 "description": "Write OpenAPI/Swagger spec for the new API endpoints."},
                {"title": "Implement API endpoints",
                 "description": "Build the backend routes and controllers."},
                {"title": "Add input validation",
                 "description": "Validate all request parameters and return proper error messages."},
                {"title": "Write API documentation",
                 "description": "Update API docs with examples and usage instructions."},
                {"title": "Add API tests",
                 "description": "Write integration tests for all new endpoints."},
            ]

        if any(w in idea_lower for w in ["dashboard", "admin", "panel", "analytics"]):
            return [
                {"title": "Design dashboard layout",
                 "description": "Create wireframes for the dashboard layout and widgets."},
                {"title": "Build data fetching layer",
                 "description": "Create API calls to fetch dashboard data."},
                {"title": "Implement dashboard UI",
                 "description": "Build the dashboard components and layout."},
                {"title": "Add charts and visualizations",
                 "description": "Integrate charting library and display data visualizations."},
                {"title": "Add dashboard tests",
                 "description": "Write tests for dashboard components and data fetching."},
            ]

        # Generic fallback
        return [
            {"title": "Research and plan implementation",
             "description": f"Research the best approach for implementing '{idea}'."},
            {"title": "Design the solution architecture",
             "description": f"Create architecture diagrams and data models for '{idea}'."},
            {"title": "Implement the core functionality",
             "description": f"Build the main implementation for '{idea}'."},
            {"title": "Add tests",
             "description": f"Write unit and integration tests for '{idea}'."},
            {"title": "Update documentation",
             "description": f"Document the new feature and update README."},
        ]

    def _feature_template(self, idea: str, tasks: list) -> str:
        task_list = "\n".join(
            f"- [ ] #{i+1} {t['title']}" for i, t in enumerate(tasks)
        )
        return f"""## Feature: {idea}

### Description
{idea}

### Sub-tasks
{task_list}

### Acceptance Criteria
- [ ] All sub-tasks completed
- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] Code reviewed

---
*Generated by GitHub Automation Bot*"""

    def run(self, ideas: list) -> list:
        """Plan multiple features."""
        results = []
        for idea in ideas:
            print(f"  🚀 Planning feature: {idea[:60]}...")
            result = self.plan_feature(idea)
            results.append(result)
        return results


# ─── Main Entry Point ────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="GitHub Automation Bot — full repo management"
    )
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--token", required=True, help="GitHub Personal Access Token")
    parser.add_argument("--mode", choices=["triage", "merge", "plan", "all"],
                        default="all", help="Automation mode")
    parser.add_argument("--idea", help="Feature idea to plan (for --mode plan)")
    parser.add_argument("--limit", type=int, default=20,
                        help="Max issues/PRs to process")
    args = parser.parse_args()

    api = GitHubAPI(args.token, args.repo)
    print(f"🤖 GitHub Automation Bot — connected to {args.repo}")
    print(f"   Mode: {args.mode}")
    print()

    if args.mode in ("triage", "all"):
        print("=== Issue Triage ===")
        triage = TriageEngine(api)
        triage.run(limit=args.limit)
        print()

    if args.mode in ("merge", "all"):
        print("=== PR Auto-Merge ===")
        merger = AutoMergeEngine(api)
        merger.run(limit=args.limit)
        print()

    if args.mode in ("plan", "all"):
        print("=== Feature Planning ===")
        planner = FeaturePlanner(api)
        if args.idea:
            planner.plan_feature(args.idea)
        else:
            # Check for feature ideas in issues labeled "feature-request"
            ideas = []
            feature_issues = api.list_issues(labels="feature-request",
                                             state="open")
            for issue in feature_issues:
                ideas.append(issue["title"])
            if ideas:
                planner.run(ideas)
            else:
                print("  No feature ideas found. Use --idea 'Your feature' to plan one.")
        print()

    print("✅ Automation complete!")


if __name__ == "__main__":
    main()
