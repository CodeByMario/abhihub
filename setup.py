#!/usr/bin/env python3
"""
One-time setup script for GitHub Automation Bot
===============================================
Configures your repo with:
  - Standardized labels (with colors and descriptions)
  - Issue templates (bug report, feature request)
  - PR template
  - Branch protection rules
  - GitHub Actions workflows
  - Dependabot configuration

Usage:
  python setup.py --repo owner/repo --token $GITHUB_TOKEN
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

# ─── Configuration ───────────────────────────────────────────────────────────

CONFIG_DIR = Path(__file__).parent / "config"

with open(CONFIG_DIR / "labels.json") as f:
    LABELS = json.load(f)

# ─── GitHub API Client ───────────────────────────────────────────────────────


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

    def _put(self, path: str, data: dict) -> dict:
        resp = requests.put(f"{self.base}{path}", headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> dict:
        resp = requests.delete(f"{self.base}{path}", headers=self.headers)
        if resp.status_code == 204:
            return {}
        resp.raise_for_status()
        return resp.json()

    def list_labels(self) -> list:
        return self._get("/labels", {"per_page": 100})

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return self._post("/labels", {
            "name": name, "color": color, "description": description
        })

    def delete_label(self, name: str) -> dict:
        return self._delete(f"/labels/{name}")

    def update_label(self, name: str, color: str, description: str = "") -> dict:
        return self._patch(f"/labels/{name}", {
            "new_name": name, "color": color, "description": description
        })

    def get_repo(self) -> dict:
        return self._get("")

    def get_default_branch(self) -> str:
        return self.get_repo()["default_branch"]

    def get_branch_protection(self, branch: str) -> dict:
        try:
            return self._get(f"/branches/{branch}/protection")
        except requests.HTTPError:
            return None

    def set_branch_protection(self, branch: str, config: dict) -> dict:
        return self._put(f"/branches/{branch}/protection", config)

    def create_file(self, path: str, content: str, message: str = "") -> dict:
        """Create a file via the GitHub API."""
        import base64
        encoded = base64.b64encode(content.encode()).decode()
        return self._put(f"/contents/{path}", {
            "message": message or f"Add {path}",
            "content": encoded,
        })

    def update_file(self, path: str, content: str, sha: str,
                    message: str = "") -> dict:
        """Update an existing file via the GitHub API."""
        import base64
        encoded = base64.b64encode(content.encode()).decode()
        return self._put(f"/contents/{path}", {
            "message": message or f"Update {path}",
            "content": encoded,
            "sha": sha,
        })

    def get_file(self, path: str) -> dict:
        """Get file metadata and content."""
        try:
            return self._get(f"/contents/{path}")
        except requests.HTTPError:
            return None


# ─── Setup Functions ─────────────────────────────────────────────────────────


def setup_labels(api: GitHubAPI) -> dict:
    """Create or update standardized labels."""
    print("\n=== Setting up labels ===")

    # Get existing labels
    existing = {l["name"]: l for l in api.list_labels()}

    results = {"created": [], "updated": [], "skipped": []}

    for label_def in LABELS:
        name = label_def["name"]
        color = label_def["color"]
        desc = label_def.get("description", "")

        if name in existing:
            # Update if color or description changed
            existing_label = existing[name]
            if (existing_label.get("color") != color or
                existing_label.get("description") != desc):
                api.update_label(name, color, desc)
                results["updated"].append(name)
                print(f"  🔄 Updated: {name}")
            else:
                results["skipped"].append(name)
                print(f"  ✅ Already configured: {name}")
        else:
            api.create_label(name, color, desc)
            results["created"].append(name)
            print(f"  ✨ Created: {name}")

    return results


def setup_templates(api: GitHubAPI) -> dict:
    """Upload issue and PR templates."""
    print("\n=== Setting up templates ===")

    templates_dir = Path(__file__).parent / ".github"
    results = {"uploaded": [], "skipped": []}

    # Issue templates
    issue_templates = [
        ("ISSUE_TEMPLATE/bug_report.md", "bug_report.md"),
        ("ISSUE_TEMPLATE/feature_request.md", "feature_request.md"),
        ("ISSUE_TEMPLATE/config.yml", "config.yml"),
    ]

    for local_path, remote_path in issue_templates:
        full_path = templates_dir / local_path
        if not full_path.exists():
            print(f"  ⚠️  Template not found: {local_path}")
            continue

        content = full_path.read_text()
        existing = api.get_file(remote_path)

        if existing:
            # Check if content changed
            import base64
            existing_content = base64.b64decode(existing["content"]).decode()
            if existing_content == content:
                results["skipped"].append(remote_path)
                print(f"  ✅ Already up to date: {remote_path}")
                continue

        api.create_file(remote_path, content, f"Add {remote_path}")
        results["uploaded"].append(remote_path)
        print(f"  ✨ Uploaded: {remote_path}")

    # PR template
    pr_template_path = templates_dir / "PULL_REQUEST_TEMPLATE.md"
    if pr_template_path.exists():
        content = pr_template_path.read_text()
        existing = api.get_file("PULL_REQUEST_TEMPLATE.md")

        if existing:
            import base64
            existing_content = base64.b64decode(existing["content"]).decode()
            if existing_content == content:
                results["skipped"].append("PULL_REQUEST_TEMPLATE.md")
                print(f"  ✅ Already up to date: PULL_REQUEST_TEMPLATE.md")
            else:
                api.update_file("PULL_REQUEST_TEMPLATE.md", content,
                               existing["sha"], "Update PR template")
                results["uploaded"].append("PULL_REQUEST_TEMPLATE.md")
                print(f"  🔄 Updated: PULL_REQUEST_TEMPLATE.md")
        else:
            api.create_file("PULL_REQUEST_TEMPLATE.md", content,
                           "Add PR template")
            results["uploaded"].append("PULL_REQUEST_TEMPLATE.md")
            print(f"  ✨ Uploaded: PULL_REQUEST_TEMPLATE.md")

    return results


def setup_workflows(api: GitHubAPI) -> dict:
    """Upload GitHub Actions workflows."""
    print("\n=== Setting up GitHub Actions workflows ===")

    workflows_dir = Path(__file__).parent / ".github" / "workflows"
    results = {"uploaded": [], "skipped": []}

    workflow_files = [
        ("auto-triage.yml", "auto-triage.yml"),
        ("auto-merge.yml", "auto-merge.yml"),
        ("feature-planning.yml", "feature-planning.yml"),
    ]

    for local_name, remote_name in workflow_files:
        local_path = workflows_dir / local_name
        remote_path = f".github/workflows/{remote_name}"

        if not local_path.exists():
            print(f"  ⚠️  Workflow not found: {local_name}")
            continue

        content = local_path.read_text()
        existing = api.get_file(remote_path)

        if existing:
            import base64
            existing_content = base64.b64decode(existing["content"]).decode()
            if existing_content == content:
                results["skipped"].append(remote_path)
                print(f"  ✅ Already up to date: {remote_path}")
                continue

        api.create_file(remote_path, content, f"Add {remote_name}")
        results["uploaded"].append(remote_path)
        print(f"  ✨ Uploaded: {remote_path}")

    return results


def setup_branch_protection(api: GitHubAPI) -> dict:
    """Configure branch protection on the default branch."""
    print("\n=== Setting up branch protection ===")

    default_branch = api.get_default_branch()
    print(f"  Default branch: {default_branch}")

    # Check if already protected
    existing = api.get_branch_protection(default_branch)
    if existing:
        print(f"  ✅ Branch '{default_branch}' is already protected")
        return {"skipped": True}

    # Configure branch protection
    protection_config = {
        "required_status_checks": {
            "strict": True,
            "contexts": ["build", "test", "lint"]
        },
        "enforce_admins": False,
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False
        },
        "restrictions": None,
        "required_conversation_resolution": True,
        "allow_auto_merge": True,
        "allow_delete": False,
        "allow_force_pushes": False,
    }

    try:
        api.set_branch_protection(default_branch, protection_config)
        print(f"  ✨ Branch protection enabled on '{default_branch}'")
        return {"enabled": True}
    except requests.HTTPError as e:
        print(f"  ⚠️  Could not set branch protection: {e}")
        return {"error": str(e)}


def setup_dependabot(api: GitHubAPI) -> dict:
    """Upload Dependabot configuration."""
    print("\n=== Setting up Dependabot ===")

    dependabot_path = Path(__file__).parent / ".github" / "dependabot.yml"
    if not dependabot_path.exists():
        print("  ⚠️  dependabot.yml not found")
        return {"skipped": True}

    content = dependabot_path.read_text()
    existing = api.get_file(".github/dependabot.yml")

    if existing:
        import base64
        existing_content = base64.b64decode(existing["content"]).decode()
        if existing_content == content:
            print("  ✅ Already up to date: .github/dependabot.yml")
            return {"skipped": True}

    api.create_file(".github/dependabot.yml", content, "Add Dependabot config")
    print("  ✨ Uploaded: .github/dependabot.yml")
    return {"uploaded": True}


def setup_secrets_instructions() -> None:
    """Print instructions for setting up secrets."""
    print("\n=== Secrets Setup Required ===")
    print("To enable the automation workflows, add these secrets to your repo:")
    print("  Settings → Secrets and variables → Actions → New repository secret")
    print()
    print("  1. GITHUB_TOKEN  (automatically available, but you can use a PAT)")
    print("     - Or use the built-in 'permissions' in workflow files")
    print()
    print("  2. OPENROUTER_API_KEY  (for AI-powered feature planning)")
    print("     - Get at: https://openrouter.ai/keys")
    print()
    print("  3. CODE_REVIEWER  (optional, for auto-assignment)")
    print("     - Comma-separated GitHub usernames to assign issues to")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Set up GitHub Automation Bot on your repo"
    )
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--token", required=True, help="GitHub Personal Access Token")
    parser.add_argument("--skip-protection", action="store_true",
                        help="Skip branch protection setup")
    parser.add_argument("--skip-workflows", action="store_true",
                        help="Skip workflow setup")
    args = parser.parse_args()

    api = GitHubAPI(args.token, args.repo)

    print(f"🚀 Setting up GitHub Automation Bot for {args.repo}")
    print(f"   Repository: https://github.com/{args.repo}")

    # Verify repo exists
    try:
        repo_info = api.get_repo()
        print(f"   Language: {repo_info.get('language', 'N/A')}")
        print(f"   Stars: {repo_info.get('stargazers_count', 0)}")
        print(f"   Private: {repo_info.get('private', False)}")
    except requests.HTTPError as e:
        print(f"❌ Error accessing repository: {e}")
        print("   Make sure the token has 'repo' scope and the repo exists.")
        sys.exit(1)

    # Run setup steps
    setup_labels(api)
    setup_templates(api)

    if not args.skip_workflows:
        setup_workflows(api)

    setup_dependabot(api)

    if not args.skip_protection:
        setup_branch_protection(api)

    setup_secrets_instructions()

    print("\n" + "=" * 60)
    print("✅ Setup complete!")
    print("=" * 60)
    print()
    print("Your repository is now configured with:")
    print("  • Standardized labels (bug, enhancement, priority, etc.)")
    print("  • Issue templates (bug report, feature request)")
    print("  • PR template with checklist")
    print("  • Auto-triage workflow (runs on new issues)")
    print("  • Auto-merge workflow (runs on PRs)")
    print("  • Feature planning workflow")
    print("  • Branch protection on the default branch")
    print("  • Dependabot for dependency updates")
    print()
    print("Next steps:")
    print(f"  1. Visit https://github.com/{args.repo}/settings/secrets")
    print("     and add the required secrets")
    print(f"  2. Visit https://github.com/{args.repo}/actions")
    print("     to see the workflows in action")
    print(f"  3. Create a test issue to see auto-triage in action!")
    print()


if __name__ == "__main__":
    main()
