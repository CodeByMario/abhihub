#!/usr/bin/env python3
"""
Smart Issue Assignment Script
=============================
Analyzes issue content and assigns to the most appropriate contributor
based on component expertise, past contributions, and workload.

Usage:
  python scripts/auto_assign.py --repo owner/repo --token $GITHUB_TOKEN --issue 42
  python scripts/auto_assign.py --repo owner/repo --token $GITHUB_TOKEN --all
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

# ─── Configuration ───────────────────────────────────────────────────────────

CONFIG_DIR = Path(__file__).parent.parent / "config"

# Load contributor expertise mapping
CONTRIBUTORS_FILE = CONFIG_DIR / "contributors.json"
if CONTRIBUTORS_FILE.exists():
    with open(CONTRIBUTORS_FILE) as f:
        CONTRIBUTORS = json.load(f)
else:
    CONTRIBUTORS = {}

# Component → expertise keywords mapping
COMPONENT_KEYWORDS = {
    "frontend": ["ui", "ux", "css", "html", "react", "vue", "angular",
                 "frontend", "button", "page", "layout", "design", "style"],
    "backend": ["api", "server", "database", "db", "sql", "backend",
                "endpoint", "express", "django", "flask", "node", "python",
                "java", "go", "rust"],
    "mobile": ["mobile", "ios", "android", "app", "react native",
               "flutter", "swift", "kotlin", "xcode"],
    "devops": ["ci", "cd", "deploy", "docker", "kubernetes", "k8s",
               "terraform", "aws", "azure", "gcp", "pipeline", "ci/cd",
               "jenkins", "github actions"],
    "testing": ["test", "testing", "unit test", "integration test",
                "e2e", "cypress", "jest", "pytest", "qa", "coverage"],
    "documentation": ["doc", "documentation", "readme", "example",
                      "guide", "tutorial", "api doc"],
    "security": ["security", "vulnerability", "auth", "authentication",
                 "authorization", "oauth", "jwt", "encryption"],
}


# ─── GitHub API ──────────────────────────────────────────────────────────────


class GitHubAPI:
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
        resp = requests.get(f"{self.base}{path}", headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict) -> dict:
        resp = requests.post(f"{self.base}{path}", headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, data: dict) -> dict:
        resp = requests.patch(f"{self.base}{path}", headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def get_issue(self, number: int) -> dict:
        return self._get(f"/issues/{number}")

    def get_contributors(self) -> list:
        """Get repo contributors sorted by contribution count."""
        return self._get("/contributors", {"per_page": 100})

    def get_collaborators(self) -> list:
        """Get repo collaborators."""
        return self._get("/collaborators", {"per_page": 100})

    def add_assignees(self, number: int, assignees: list) -> dict:
        return self._post(f"/issues/{number}/assignees", {"assignees": assignees})

    def add_comment(self, number: int, body: str) -> dict:
        return self._post(f"/issues/{number}/comments", {"body": body})

    def list_issues(self, state: str = "open", assignee: str = None,
                    labels: str = None, per_page: int = 100) -> list:
        params = {"state": state, "per_page": per_page}
        if assignee:
            params["assignee"] = assignee
        if labels:
            params["labels"] = labels
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

    def get_user(self, username: str) -> dict:
        """Get user info from GitHub API."""
        resp = requests.get(
            f"https://api.github.com/users/{username}",
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()


# ─── Assignment Engine ───────────────────────────────────────────────────────


class AssignmentEngine:
    """Intelligently assigns issues to contributors."""

    def __init__(self, api: GitHubAPI):
        self.api = api
        self.contributors = self._load_contributors()

    def _load_contributors(self) -> dict:
        """Load contributor expertise and build workload map."""
        # Start with configured contributors
        contributors = dict(CONTRIBUTORS)

        # Get actual repo contributors
        try:
            repo_contributors = self.api.get_contributors()
            for c in repo_contributors:
                login = c["login"]
                if login not in contributors:
                    contributors[login] = {"expertise": [], "max_issues": 5}
        except requests.HTTPError:
            pass

        # Get collaborators
        try:
            collabs = self.api.get_collaborators()
            for c in collabs:
                login = c["login"]
                if login not in contributors:
                    contributors[login] = {"expertise": [], "max_issues": 5}
        except requests.HTTPError:
            pass

        # Build workload map
        workload = {}
        for login in contributors:
            open_issues = self.api.list_issues(state="open", assignee=login)
            workload[login] = len(open_issues)

        return {"experts": contributors, "workload": workload}

    def detect_components(self, title: str, body: str) -> list:
        """Detect which components an issue relates to."""
        text = (title + " " + body).lower()
        components = []
        for component, keywords in COMPONENT_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                components.append(component)
        return components

    def suggest_assignee(self, issue: dict) -> str:
        """Suggest the best assignee for an issue."""
        title = issue.get("title", "")
        body = issue.get("body") or ""
        components = self.detect_components(title, body)

        # Strategy 1: Component-based assignment
        for component in components:
            for person, info in self.contributors["experts"].items():
                expertise = info.get("expertise", [])
                if isinstance(expertise, list) and component in expertise:
                    workload = self.contributors["workload"].get(person, 0)
                    max_issues = info.get("max_issues", 5)
                    if workload < max_issues:
                        return person

        # Strategy 2: Keyword-based assignment
        text = (title + " " + body).lower()
        for person, info in self.contributors["experts"].items():
            expertise = info.get("expertise", [])
            if isinstance(expertise, list):
                for kw in expertise:
                    if isinstance(kw, str) and kw in text:
                        workload = self.contributors["workload"].get(person, 0)
                        max_issues = info.get("max_issues", 5)
                        if workload < max_issues:
                            return person

        # Strategy 3: Least busy contributor
        available = [
            (person, self.contributors["workload"].get(person, 0))
            for person in self.contributors["experts"]
            if self.contributors["workload"].get(person, 0) <
               self.contributors["experts"][person].get("max_issues", 5)
        ]
        if available:
            available.sort(key=lambda x: x[1])
            return available[0][0]

        # Strategy 4: Default assignee
        return self.contributors["experts"].get("default")

    def assign_issue(self, issue: dict) -> dict:
        """Assign an issue to a contributor."""
        number = issue["number"]
        title = issue["title"]

        # Skip if already assigned
        if issue.get("assignees"):
            return {"issue": number, "skipped": True, "reason": "Already assigned"}

        # Skip if has do-not-assign label
        labels = {l["name"] for l in issue.get("labels", [])}
        if "do-not-assign" in labels:
            return {"issue": number, "skipped": True, "reason": "do-not-assign label"}

        assignee = self.suggest_assignee(issue)

        if not assignee:
            return {"issue": number, "skipped": True, "reason": "No suitable assignee found"}

        try:
            self.api.add_assignees(number, [assignee])

            # Comment with assignment reason
            components = self.detect_components(title, issue.get("body") or "")
            reason = f"Auto-assigned based on expertise: {', '.join(components) if components else 'general triage'}"
            comment = f"""## 🤖 Auto-Assignment

This issue has been automatically assigned to **@{assignee}**.

**Reason:** {reason}

**Current workload:** {self.contributors['workload'].get(assignee, 0)} open issues

If you're unable to work on this, please unassign yourself or comment and a maintainer will reassign.

*Assigned by GitHub Automation Bot at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*"""
            self.api.add_comment(number, comment)

            return {"issue": number, "assigned_to": assignee, "success": True}
        except requests.HTTPError as e:
            return {"issue": number, "error": str(e)}

    def run(self, limit: int = 20) -> list:
        """Assign all unassigned open issues."""
        issues = self.api.list_issues(state="open", per_page=limit)
        unassigned = [i for i in issues if not i.get("assignees")]

        results = []
        for issue in unassigned:
            result = self.assign_issue(issue)
            if result.get("success"):
                print(f"  ✅ Assigned #{issue['number']} to @{result['assigned_to']}")
            elif result.get("skipped"):
                print(f"  ⏭️  Skipped #{issue['number']}: {result['reason']}")
            else:
                print(f"  ❌ Error #{issue['number']}: {result.get('error', 'unknown')}")
            results.append(result)

        return results


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Smart issue assignment for GitHub"
    )
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--token", required=True, help="GitHub PAT")
    parser.add_argument("--issue", type=int, help="Specific issue number to assign")
    parser.add_argument("--all", action="store_true",
                        help="Assign all unassigned issues")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    api = GitHubAPI(args.token, args.repo)
    engine = AssignmentEngine(api)

    if args.issue:
        issue = api.get_issue(args.issue)
        result = engine.assign_issue(issue)
        print(json.dumps(result, indent=2))
    elif args.all:
        results = engine.run(limit=args.limit)
        print(f"\nProcessed {len(results)} issues")
    else:
        print("Use --issue N or --all")


if __name__ == "__main__":
    main()
