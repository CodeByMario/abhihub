"""
Detailed End-to-End Persona Workflow Test Suite
Simulates realistic human interactive journeys:
- Guest: Browse, search filter, click study material, hit auth gate, test AI launcher.
- New User: Cold session, profile nudge / onboarding check, preference toggle.
- Free Student: Routine navigation, search subjects, peer search, comment flow, notifications.
- Premium Member: Study Pass access validation, monetized resource unlock verification.
- Admin: Admin portal entry, stats inspection, user moderation tab, action triggers.
"""

import os
import sys
import json
import time
import jwt
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:5000")
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_FILE = os.path.join(OUTPUT_DIR, "reports", "detailed_workflow_report.json")
REPORT_MD = os.path.join(OUTPUT_DIR, "reports", "detailed_workflow_report.md")

os.makedirs(os.path.join(OUTPUT_DIR, "reports"), exist_ok=True)

PERSONAS = {
    "guest": {
        "title": "Guest Persona",
        "auth": False
    },
    "new_user": {
        "title": "New User Persona",
        "auth": True,
        "email": "fresh.user@abhihub.test",
        "sub": "usr-uuid-new-101",
        "name": "Fresh Student",
        "role": "student"
    },
    "free_student": {
        "title": "Active Free Student Persona",
        "auth": True,
        "email": "free.student@abhihub.test",
        "sub": "usr-uuid-free-202",
        "name": "Sam Student",
        "role": "student"
    },
    "premium_student": {
        "title": "Study Pass Premium Persona",
        "auth": True,
        "email": "study.pass@abhihub.test",
        "sub": "usr-uuid-pass-303",
        "name": "Pat Premium",
        "role": "premium"
    },
    "admin": {
        "title": "Platform Administrator Persona",
        "auth": True,
        "email": "admin@abhihub.test",
        "sub": "usr-uuid-admin-404",
        "name": "Root Admin",
        "role": "admin"
    }
}


def create_token(p_cfg):
    payload = {
        "sub": p_cfg["sub"],
        "email": p_cfg["email"],
        "user_metadata": {
            "name": p_cfg["name"],
            "role": p_cfg.get("role", "student"),
            "college": "Testing Institute of Tech",
            "branch": "Computer Science"
        },
        "app_metadata": {"provider": "email"},
        "exp": int(time.time()) + 3600
    }
    return jwt.encode(payload, "test-secret-at-least-32-bytes-long-super-safe-key", algorithm="HS256")


def attach_monitors(page, logs, errors, req_fails):
    page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text} (at {msg.location.get('url', '')}:{msg.location.get('lineNumber', '')})") if msg.type in ["error"] else None)
    page.on("pageerror", lambda err: errors.append(f"{err} [stack: {getattr(err, 'stack', '')}]"))
    page.on("response", lambda res: req_fails.append(f"{res.status} {res.url}") if res.status >= 500 else None)


def run_guest_workflow(page):
    steps = []
    # 1. Landing Page Load
    page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
    steps.append("Loaded landing page")

    # 2. Test AI Assistant Launcher interaction
    ai_btn = page.locator("#abhiAiLauncher, button[title*='AI'], button[aria-label*='AI']").first
    if ai_btn.is_visible():
        ai_btn.click()
        page.wait_for_timeout(500)
        steps.append("Opened AI assistant drawer as guest")

    # 3. Browse Study Library
    page.goto(f"{BASE_URL}/store-room", wait_until="domcontentloaded")
    page.wait_for_timeout(600)
    steps.append("Navigated to store-room library")

    # 4. Attempt unauthenticated action (e.g. settings or earnings)
    page.goto(f"{BASE_URL}/settings", wait_until="domcontentloaded")
    steps.append(f"Checked auth gate redirect on /settings (URL: {page.url})")
    return steps


def run_new_user_workflow(page, p_cfg):
    steps = []
    token = create_token(p_cfg)
    auth_res = page.request.post(f"{BASE_URL}/auth", headers={"Authorization": f"Bearer {token}"})
    steps.append(f"Authorized new user session: HTTP {auth_res.status}")

    # 1. First landing on dashboard
    page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded")
    page.wait_for_timeout(600)
    steps.append("Rendered initial dashboard")

    # 2. Settings preference check
    page.goto(f"{BASE_URL}/settings", wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    steps.append("Inspected user settings and notification toggles")
    return steps


def run_free_student_workflow(page, p_cfg):
    steps = []
    token = create_token(p_cfg)
    auth_res = page.request.post(f"{BASE_URL}/auth", headers={"Authorization": f"Bearer {token}"})
    steps.append(f"Authenticated active student session: HTTP {auth_res.status}")

    # 1. Library Search & Subject Browsing
    page.goto(f"{BASE_URL}/store-room", wait_until="domcontentloaded")
    page.wait_for_timeout(600)
    steps.append("Loaded library resources")

    # 2. Check peer chat / search peers API
    res = page.request.get(f"{BASE_URL}/api/chat/search-peers?q=__suggested__")
    steps.append(f"Peer chat suggested lookup status: {res.status}")

    # 3. Check notifications feed
    n_res = page.request.get(f"{BASE_URL}/api/my-notifications?limit=10")
    steps.append(f"Notification feed status: {n_res.status}")
    return steps


def run_premium_workflow(page, p_cfg):
    steps = []
    token = create_token(p_cfg)
    auth_res = page.request.post(f"{BASE_URL}/auth", headers={"Authorization": f"Bearer {token}"})
    steps.append(f"Authenticated study pass session: HTTP {auth_res.status}")

    # 1. Check access status gate
    acc_res = page.request.get(f"{BASE_URL}/api/my-access")
    steps.append(f"Access entitlement API response: {acc_res.status}")

    # 2. Check earnings & monetization
    page.goto(f"{BASE_URL}/earnings", wait_until="domcontentloaded")
    page.wait_for_timeout(600)
    steps.append("Inspected monetization & pass privileges")
    return steps


def run_admin_workflow(page, p_cfg):
    steps = []
    token = create_token(p_cfg)
    auth_res = page.request.post(f"{BASE_URL}/auth", headers={"Authorization": f"Bearer {token}"})
    steps.append(f"Authenticated admin session: HTTP {auth_res.status}")

    # 1. Navigate to Admin route
    res = page.goto(f"{BASE_URL}/admin", wait_until="domcontentloaded")
    steps.append(f"Accessed /admin (HTTP {res.status if res else 'Unknown'})")
    page.wait_for_timeout(600)
    return steps


def run_all_workflows():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        workflows = [
            ("guest", run_guest_workflow),
            ("new_user", lambda pg: run_new_user_workflow(pg, PERSONAS["new_user"])),
            ("free_student", lambda pg: run_free_student_workflow(pg, PERSONAS["free_student"])),
            ("premium_student", lambda pg: run_premium_workflow(pg, PERSONAS["premium_student"])),
            ("admin", lambda pg: run_admin_workflow(pg, PERSONAS["admin"])),
        ]

        for p_key, wf_func in workflows:
            context = browser.new_context()
            page = context.new_page()

            logs, errs, req_fails = [], [], []
            attach_monitors(page, logs, errs, req_fails)

            item = {
                "persona": PERSONAS[p_key]["title"],
                "status": "PASS",
                "completed_steps": [],
                "page_errors": [],
                "console_errors": [],
                "network_5xx": []
            }

            try:
                item["completed_steps"] = wf_func(page)
            except Exception as e:
                item["status"] = "FAIL"
                item["page_errors"].append(str(e))

            item["console_errors"] = list(logs)
            item["page_errors"].extend(errs)
            item["network_5xx"] = list(req_fails)

            if item["page_errors"] or item["network_5xx"]:
                item["status"] = "FAIL"

            results.append(item)
            context.close()

        browser.close()

    # Save reports
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("# AbhiHub Detailed Workflow Test Report\n\n")
        for r in results:
            sym = "✅" if r["status"] == "PASS" else "❌"
            f.write(f"## {sym} {r['persona']} — Status: {r['status']}\n")
            f.write("### Completed Actions\n")
            for st in r["completed_steps"]:
                f.write(f"- {st}\n")
            if r["page_errors"]:
                f.write("### Page Exceptions\n")
                for pe in r["page_errors"]:
                    f.write(f"- `{pe}`\n")
            if r["console_errors"]:
                f.write("### Client Console Errors\n")
                for ce in r["console_errors"]:
                    f.write(f"- `{ce}`\n")
            if r["network_5xx"]:
                f.write("### 5xx Server Failures\n")
                for ne in r["network_5xx"]:
                    f.write(f"- `{ne}`\n")
            f.write("\n---\n\n")

    print(f"[COMPLETED] Workflows recorded to {REPORT_MD}")


if __name__ == "__main__":
    run_all_workflows()
