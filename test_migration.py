import requests
import time

PORT = 5000
BASE_URL = f"http://localhost:{PORT}"

def test_suspect():
    print("Testing /api/report-suspect...")
    res = requests.post(f"{BASE_URL}/api/report-suspect", json={'action': 'screenshot detected'})
    print(f"Status Code: {res.status_code}, Response: {res.text}")

def test_rank():
    print("Testing /rank...")
    res = requests.get(f"{BASE_URL}/rank")
    print(f"Status Code: {res.status_code}")
    print("Rank response (truncated):", res.text[:200])

if __name__ == "__main__":
    time.sleep(1) # wait for reload if any
    test_suspect()
    test_rank()
