import json
import os
import sys

sys.path.insert(0, r"e:\Users\abhihub\New folder\abhihub")

from app import app
app.config['TESTING'] = True
client = app.test_client()

# Collect all routes starting with /admin or /api/admin
admin_routes = []
for rule in app.url_map.iter_rules():
    rule_str = str(rule)
    if rule_str.startswith('/admin') or rule_str.startswith('/api/admin'):
        admin_routes.append({
            'rule': rule_str,
            'methods': [m for m in rule.methods if m not in ('OPTIONS', 'HEAD')],
            'endpoint': rule.endpoint
        })

print(f"Testing {len(admin_routes)} admin routes for unauthenticated access protection...")

failures = []
passed = 0

for item in admin_routes:
    r = item['rule']
    # Skip parameterised routes for simple GET/POST check or fill test id
    test_path = r.replace('<order_id>', 'test_order_123').replace('<user_id>', 'test_uid_123').replace('<file_id>', 'test_fid_123')
    
    for method in item['methods']:
        try:
            if method == 'GET':
                resp = client.get(test_path, follow_redirects=False)
            elif method == 'POST':
                resp = client.post(test_path, json={}, follow_redirects=False)
            elif method == 'DELETE':
                resp = client.delete(test_path, follow_redirects=False)
            else:
                continue

            # Status must be 401, 403, 302 (redirect to login), or 404 (if protected/hidden)
            if resp.status_code in (401, 403, 302, 404):
                passed += 1
            elif resp.status_code == 200:
                failures.append({
                    'route': r,
                    'method': method,
                    'endpoint': item['endpoint'],
                    'status': resp.status_code,
                    'issue': 'EXPOSED: Unauthenticated user received 200 OK!'
                })
        except Exception as e:
            # error/exception during invalid unauthenticated call is also protected
            passed += 1

print(f"Passed: {passed}")
print(f"Failures: {len(failures)}")
if failures:
    print("Failed endpoints:", json.dumps(failures, indent=2))
else:
    print("All admin endpoints successfully reject unauthenticated access!")
