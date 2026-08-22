#!/usr/bin/env python3
"""
Feature Planning Script
=======================
Breaks down feature ideas into structured, actionable GitHub issues.
Uses keyword analysis to generate appropriate sub-tasks.

Usage:
  python scripts/feature_planner.py --repo owner/repo --token $GITHUB_TOKEN --idea "Add dark mode"
  python scripts/feature_planner.py --repo owner/repo --token $GITHUB_TOKEN --from-issues
"""

import argparse
import json
import sys
from pathlib import Path

import requests


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

    def _post(self, path: str, data: dict) -> dict:
        resp = requests.post(f"{self.base}{path}", headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str, params: dict = None) -> dict:
        resp = requests.get(f"{self.base}{path}", headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def create_issue(self, title: str, body: str, labels: list = None) -> dict:
        data = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        return self._post("/issues", data)

    def add_comment(self, number: int, body: str) -> dict:
        return self._post(f"/issues/{number}/comments", {"body": body})

    def list_issues(self, state: str = "open", labels: str = None,
                    per_page: int = 100) -> list:
        params = {"state": state, "per_page": per_page}
        if labels:
            params["labels"] = labels
        return self._get("/issues", params=params)


# ─── Feature Breakdown Engine ────────────────────────────────────────────────


class FeaturePlanner:
    """Breaks down feature ideas into sub-tasks."""

    def __init__(self, api: GitHubAPI):
        self.api = api

    def break_down(self, idea: str) -> list:
        """Break a feature idea into sub-tasks based on keyword analysis."""
        idea_lower = idea.lower()

        # ─── Predefined breakdowns for common feature types ───
        breakdowns = {
            "auth": (["login", "auth", "sign in", "register", "signup"], [
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
            ]),
            "dark_mode": (["dark mode", "theme", "color scheme", "dark theme"], [
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
            ]),
            "api": (["api", "endpoint", "rest", "graphql", "webhook"], [
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
            ]),
            "dashboard": (["dashboard", "admin", "panel", "analytics", "metrics"], [
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
            ]),
            "search": (["search", "filter", "query", "elasticsearch", "solr"], [
                {"title": "Design search UI",
                 "description": "Create search bar and results display components."},
                {"title": "Implement search backend",
                 "description": "Build search indexing and query processing."},
                {"title": "Add search filters",
                 "description": "Implement faceted search with filters."},
                {"title": "Add search tests",
                 "description": "Write tests for search functionality."},
                {"title": "Optimize search performance",
                 "description": "Add caching and performance optimizations."},
            ]),
            "notification": (["notification", "email", "sms", "push", "alert"], [
                {"title": "Design notification system architecture",
                 "description": "Plan notification delivery channels and queues."},
                {"title": "Implement notification backend",
                 "description": "Build notification creation and delivery system."},
                {"title": "Add notification UI",
                 "description": "Create notification center in the UI."},
                {"title": "Add notification tests",
                 "description": "Write tests for notification delivery."},
                {"title": "Set up email templates",
                 "description": "Design and implement email notification templates."},
            ]),
        }

        # Try to match the idea to a predefined breakdown
        for _, (keywords, tasks) in breakdowns.items():
            if any(kw in idea_lower for kw in keywords):
                return tasks

        # ─── Generic fallback breakdown ───
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

    def plan_feature(self, idea: str) -> dict:
        """Plan a feature: create parent issue + sub-task issues."""
        tasks = self.break_down(idea)

        # Create parent tracking issue
        task_list = "\n".join(
            f"- [ ] {t['title']}" for t in tasks
        )
        parent_body = f"""## 🚀 Feature: {idea}

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

        parent = self.api.create_issue(
            title=f"🚀 Feature: {idea}",
            body=parent_body,
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

            # Link to parent
            self.api.add_comment(parent["number"],
                                f"Sub-task: #{sub['number']} — {sub['title']}")

        return {"parent": parent, "sub_tasks": sub_issues}

    def plan_from_issues(self) -> list:
        """Find feature-request issues and plan them."""
        feature_issues = self.api.list_issues(
            state="open", labels="feature-request"
        )
        results = []
        for issue in feature_issues:
            print(f"  🚀 Planning feature from #{issue['number']}: {issue['title'][:50]}...")
            result = self.plan_feature(issue["title"])
            results.append(result)
        return results


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Plan features by breaking them into sub-tasks"
    )
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--token", required=True, help="GitHub PAT")
    parser.add_argument("--idea", help="Feature idea to plan")
    parser.add_argument("--from-issues", action="store_true",
                        help="Plan features from issues labeled 'feature-request'")
    args = parser.parse_args()

    api = GitHubAPI(args.token, args.repo)
    planner = FeaturePlanner(api)

    if args.idea:
        result = planner.plan_feature(args.idea)
        print(f"\n✅ Feature planned!")
        print(f"   Parent issue: #{result['parent']['number']}")
        print(f"   Sub-tasks: {len(result['sub_tasks'])}")
    elif args.from_issues:
        results = planner.plan_from_issues()
        print(f"\n✅ Planned {len(results)} features from issues")
    else:
        print("Use --idea 'Your feature' or --from-issues")


if __name__ == "__main__":
    main()
