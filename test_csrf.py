from app import app
import json

app.testing = True
client = app.test_client()

print("--- Testing API Exemption ---")
# /store-room/api/label (POST) should NOT return 400 Bad Request for missing CSRF token
response = client.post('/store-room/api/label', json={'test': 1})
if response.status_code == 400 and b'CSRF' in response.data:
    print("[FAIL] /store-room/api/label requires CSRF!")
else:
    print("[PASS] /store-room/api/label is exempted properly (Status:", response.status_code, ")")

# /upload (POST) without CSRF token SHOULD return 400 Bad Request
response = client.post('/upload', data={'test': 1})
if response.status_code == 400 and b'CSRF' in response.data:
    print("[PASS] /upload correctly blocks missing CSRF token (Status:", response.status_code, ")")
else:
    print("[FAIL] /upload did not block missing CSRF! (Status:", response.status_code, ")")
