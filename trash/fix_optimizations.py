"""
STEP 5-7 — Optimization + Simplification:
1. Add input length validation to /api/departments endpoint
2. Add get_device_type() helper to app.py (deduplicate device detection)
3. Replace both inline device detection blocks with helper call
4. Add length guard to subject_name in /api/subject-request
"""
import ast

path = r'e:\Users\abhihub\New folder\abhihub\app.py'
src = open(path, encoding='utf-8').read()
orig = src
changes = 0

def rep(old, new, label, count=1):
    global src, changes
    if old in src:
        src = src.replace(old, new, count)
        changes += 1
        print(f"  [OK] {label}")
    else:
        print(f"  [MISS] {label}")

print("--- STEP 5-7 fixes ---")

# 1. Add get_device_type() helper right after sanitize_filename function
rep(
    "def sanitize_filename(filename):\n    \"\"\"Sanitize filename to prevent path traversal and other attacks\"\"\"\n    # Remove path components\n    filename = os.path.basename(filename)\n    # Remove any potentially dangerous characters\n    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)\n    return filename",
    "def sanitize_filename(filename):\n    \"\"\"Sanitize filename to prevent path traversal and other attacks\"\"\"\n    # Remove path components\n    filename = os.path.basename(filename)\n    # Remove any potentially dangerous characters\n    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)\n    return filename\n\ndef get_device_type(user_agent: str) -> str:\n    \"\"\"Detect device type from user agent string.\"\"\"\n    ua = (user_agent or '').lower()\n    if 'mobile' in ua or 'android' in ua or 'iphone' in ua:\n        return 'mobile'\n    if 'tablet' in ua or 'ipad' in ua:\n        return 'tablet'\n    return 'desktop'",
    "Add get_device_type() helper"
)

# 2. Replace inline device detection in authorize()
rep(
    "        # Simple device type detection\n        device_type = 'desktop'\n        userAgentLower = user_agent.lower()\n        if 'mobile' in userAgentLower or 'android' in userAgentLower or 'iphone' in userAgentLower:\n            device_type = 'mobile'\n        elif 'tablet' in userAgentLower or 'ipad' in userAgentLower:\n            device_type = 'tablet'",
    "        # Simple device type detection\n        device_type = get_device_type(user_agent)",
    "authorize(): use get_device_type()"
)

# 3. Add length validation to /api/departments
rep(
    "    if not name:\n        return jsonify({'success': False, 'message': 'Department name required'}), 400\n    from methods.supabase_helper import init_supabase",
    "    if not name:\n        return jsonify({'success': False, 'message': 'Department name required'}), 400\n    if len(name) > 120 or len(abbr) > 20:\n        return jsonify({'success': False, 'message': 'Name too long (max 120) or abbreviation too long (max 20)'}), 400\n    from methods.supabase_helper import init_supabase",
    "Add length guard to /api/departments"
)

# 4. Add length guard to /api/subject-request
rep(
    "    subject_name = (data.get('subject_name') or '').strip()\n    if not subject_name:\n        return jsonify({'success': False, 'message': 'subject_name required'}), 400",
    "    subject_name = (data.get('subject_name') or '').strip()\n    if not subject_name:\n        return jsonify({'success': False, 'message': 'subject_name required'}), 400\n    if len(subject_name) > 200:\n        return jsonify({'success': False, 'message': 'Subject name too long (max 200 chars)'}), 400",
    "Add length guard to /api/subject-request"
)

# 5. Fix hardcoded default month in _get_quota
rep(
    "    db_quota = 19\n    last_reset = '2026-05'\n    if res.data:\n        db_quota = res.data[0].get('paper_quota_remaining')\n        if db_quota is None:\n            db_quota = 19\n        last_reset = res.data[0].get('last_quota_reset') or '2026-05'",
    "    db_quota = 19\n    _default_month = datetime.utcnow().strftime('%Y-%m')\n    last_reset = _default_month\n    if res.data:\n        db_quota = res.data[0].get('paper_quota_remaining')\n        if db_quota is None:\n            db_quota = 19\n        last_reset = res.data[0].get('last_quota_reset') or _default_month",
    "Fix hardcoded '2026-05' fallback in _get_quota"
)

print(f"\n{changes} replacements made")

# Write back (preserve CRLF)
raw = open(path, 'rb').read()
has_crlf = b'\r\n' in raw
if has_crlf:
    output = src.replace('\n', '\r\n') if '\r\n' not in src else src
else:
    output = src

with open(path, 'wb') as f:
    f.write(output.encode('utf-8'))

# Verify syntax
try:
    tree = ast.parse(src)
    print("Syntax OK")
except SyntaxError as e:
    print(f"SyntaxError: {e}")
