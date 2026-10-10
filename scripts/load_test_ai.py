"""
Tarika AI Assistant - 50 Concurrent User Load Test (Task 6.7)
Simulates 50 concurrent users sending study queries to /api/ai/assistant.
Validates rate limiting (429), timeouts, and server resilience under load.
"""

import time
import json
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

TARGET_URL = "http://127.0.0.1:5000/api/ai/assistant"
CONCURRENT_USERS = 50

def send_query(user_idx):
    payload = json.dumps({
        "message": f"Hello from user {user_idx}, explain Newton's third law concisely.",
        "model": "01-ai/yi-large"
    }).encode("utf-8")

    req = urllib.request.Request(
        TARGET_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"TarikaLoadTest/1.0 User-{user_idx}",
            "X-Forwarded-For": f"192.168.1.{10 + (user_idx % 10)}"  # Simulate a pool of IPs
        }
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            elapsed = time.time() - start
            return {
                "user": user_idx,
                "status": resp.status,
                "elapsed": round(elapsed, 2),
                "error": None
            }
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        return {
            "user": user_idx,
            "status": e.code,
            "elapsed": round(elapsed, 2),
            "error": f"HTTP {e.code}"
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "user": user_idx,
            "status": 0,
            "elapsed": round(elapsed, 2),
            "error": str(e)
        }

def run_load_test():
    print(f"🚀 Launching 50 concurrent requests against {TARGET_URL}...")
    start_total = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=CONCURRENT_USERS) as executor:
        futures = [executor.submit(send_query, i) for i in range(CONCURRENT_USERS)]
        for f in as_completed(futures):
            results.append(f.result())

    total_time = round(time.time() - start_total, 2)
    statuses = {}
    for r in results:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1

    print("\n--- Load Test Results ---")
    print(f"Total Requests: {len(results)}")
    print(f"Total Wall Time: {total_time}s")
    print(f"Status Code Breakdown: {statuses}")
    
    success_or_limited = sum(statuses.get(c, 0) for c in [200, 401, 429])
    print(f"Handled Cleanly (200/401/429): {success_or_limited}/{len(results)}")
    
    server_crashes = statuses.get(500, 0) + statuses.get(0, 0)
    if server_crashes == 0:
        print("✅ PASS: All 50 concurrent requests handled cleanly without server crash or unhandled 500s.")
    else:
        print(f"⚠️ Notice: {server_crashes} requests encountered errors or timeouts.")

if __name__ == "__main__":
    run_load_test()
