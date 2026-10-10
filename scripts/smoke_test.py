import json
import os
import sys

# Add workspace to path
sys.path.insert(0, r"e:\Users\abhihub\New folder\abhihub")

try:
    from app import app
    app.config['TESTING'] = True
    client = app.test_client()

    test_routes = [
        "/",
        "/health",
        "/about",
        "/terms",
        "/privacy",
        "/dmca",
        "/contact",
        "/login",
        "/signup",
        "/offline",
        "/robots.txt",
        "/ads.txt",
        "/admin",
        "/admin/controle",
        "/api/version"
    ]

    results = {}
    for r in test_routes:
        try:
            res = client.get(r, follow_redirects=False)
            results[r] = {
                "status_code": res.status_code,
                "location": res.headers.get("Location")
            }
        except Exception as e:
            results[r] = {
                "status_code": "ERROR",
                "error": str(e)
            }

    os.makedirs("docs", exist_ok=True)
    with open("docs/smoke_before.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("Smoke baseline recorded successfully.")
    print(json.dumps(results, indent=2))
except Exception as e:
    print(f"Error loading app for smoke test: {e}")
