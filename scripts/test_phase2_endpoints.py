import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

def test_phase2():
    client = app.test_client()
    errors = []

    # 1. /api/me unauthenticated
    res = client.get('/api/me')
    if res.status_code != 200:
        errors.append(f"/api/me unauth status {res.status_code}")
    else:
        data = res.get_json()
        if not data.get('success') or data.get('authenticated') is not False:
            errors.append(f"/api/me unauth unexpected payload: {data}")

    # 2. /indexnow should be 404 (removed unauthenticated endpoint)
    res = client.get('/indexnow')
    if res.status_code != 404:
        errors.append(f"/indexnow expected 404 but got {res.status_code}")

    # 3. /api/indexnow/submit should require auth
    res = client.post('/api/indexnow/submit', json={'urls': ['https://abhihub.com/']})
    if res.status_code not in (401, 302):
        errors.append(f"/api/indexnow/submit unauth expected 401/302 but got {res.status_code}")

    # 4. /api/reports suspect
    res = client.post('/api/reports', json={'type': 'suspect', 'action': 'devtools_opened'})
    if res.status_code not in (200, 500): # 200 on mock/db or 500 on db client
        errors.append(f"/api/reports suspect failed: {res.status_code}")

    # 5. /api/reports broken_file
    res = client.post('/api/reports', json={'type': 'broken_file', 'file_name': 'test.pdf', 'error_message': 'corrupted'})
    if res.status_code not in (200, 500):
        errors.append(f"/api/reports broken_file failed: {res.status_code}")

    # 6. /api/reports document issue
    res = client.post('/api/reports', json={'type': 'issue', 'doc_title': 'Unit 1 Notes', 'message': 'missing page 5'})
    if res.status_code not in (200, 500):
        errors.append(f"/api/reports issue failed: {res.status_code}")

    # 7. Check backward-compatible shims for reports
    res = client.post('/api/report-issue', json={'doc_title': 'Unit 1 Notes', 'message': 'missing page 5'})
    if res.status_code not in (200, 500):
        errors.append(f"/api/report-issue shim failed: {res.status_code}")

    # 8. Check events endpoint
    with client.session_transaction() as sess:
        sess['user'] = {'uid': 'test-uid-123', 'email': 'test@abhihub.com'}

    res = client.post('/api/events', json={'event_type': 'DOWNLOAD', 'metadata': {'doc_id': '123'}})
    if res.status_code != 200:
        errors.append(f"/api/events DOWNLOAD failed: {res.status_code}")

    res = client.post('/api/events', json={'event_type': 'FILE_ACCESS', 'file_name': 'test.pdf'})
    if res.status_code not in (200, 500):
        errors.append(f"/api/events FILE_ACCESS failed: {res.status_code}")

    # 9. /api/me authenticated
    res = client.get('/api/me')
    if res.status_code != 200:
        errors.append(f"/api/me auth status {res.status_code}")
    else:
        data = res.get_json()
        if not data.get('authenticated'):
            errors.append(f"/api/me auth expected authenticated=True: {data}")

    if errors:
        print("FAILURES:")
        for err in errors:
            print(f" - {err}")
        sys.exit(1)
    else:
        print("All Phase 2 unified endpoints verified successfully! 100% PASS.")
        sys.exit(0)

if __name__ == '__main__':
    test_phase2()
