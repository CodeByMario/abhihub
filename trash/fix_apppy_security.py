"""
STEP 2 — Security fixes for app.py:
1. CSRF TIME_LIMIT: None -> 3600
2. Admin emails: hardcoded list -> env variable
3. Remove duplicate imports at line 372-374 (logging, json already at top)
4. Fix inline `from datetime import datetime` inside _recent_year_boost
"""
import ast

path = r'e:\Users\abhihub\New folder\abhihub\app.py'
raw = open(path, 'rb').read()
src = raw.decode('utf-8').replace('\r\n', '\n')
changes = 0

def rep(old, new, label, count=1):
    global src, changes
    if old in src:
        src = src.replace(old, new, count)
        changes += 1
        print(f"  [OK] {label}")
    else:
        print(f"  [MISS] {label}: not found")

print("--- Applying security + dedup fixes to app.py ---")

# 1. CSRF TIME_LIMIT
rep(
    "app.config['WTF_CSRF_TIME_LIMIT'] = None  # No time limit on CSRF tokens",
    "app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour expiry on CSRF tokens",
    "CSRF TIME_LIMIT None -> 3600"
)

# 2a. Read admin emails from env, build list constant
# Replace: ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'abhijeetshende4053@gmail.com')
rep(
    "# Admin email from environment variable\nADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'abhijeetshende4053@gmail.com')",
    "# Admin emails from environment variable (comma-separated)\nADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'abhijeetshende4053@gmail.com')\nADMIN_EMAILS = [e.strip().lower() for e in os.getenv('ADMIN_EMAILS', 'abhijeetshende4053@gmail.com,codebymario@gmail.com').split(',') if e.strip()]",
    "Add ADMIN_EMAILS list from env"
)

# 2b. Replace hardcoded list in admin_required
rep(
    "        if user_email not in ['abhijeetshende4053@gmail.com', 'codebymario@gmail.com']:\n            abort(403)  # Forbidden",
    "        if user_email not in ADMIN_EMAILS:\n            abort(403)  # Forbidden",
    "admin_required: use ADMIN_EMAILS constant"
)

# 2c. Replace hardcoded list in _consume_credit
rep(
    "    if user_email in ['abhijeetshende4053@gmail.com', 'codebymario@gmail.com']:\n        return True",
    "    if user_email in ADMIN_EMAILS:\n        return True",
    "_consume_credit: use ADMIN_EMAILS constant"
)

# 3. Remove duplicate `import logging` at line ~372 (already imported at line 11)
rep(
    "\nimport logging\nfrom PIL import Image\nimport json\nimport jwt",
    "\nfrom PIL import Image\nimport jwt",
    "Remove duplicate `import logging` + `import json` (already at top)"
)

# 4. Fix inline `from datetime import datetime` inside _recent_year_boost
rep(
    "    from datetime import datetime\n    now_year = datetime.now().year",
    "    now_year = datetime.now().year",
    "Remove inline `from datetime import datetime` (already imported)"
)

# 5. Remove duplicate `import json` at line ~31 (inside firebase block)
# It's inside an if block, so keep it but move to top later — just flag it
print("  [INFO] `import json` inside firebase init block (line ~31) — safe to remove since json already imported at top")
rep(
    "    # Load from environment variable (recommended for production)\n    import json\n    cred_dict = json.loads(firebase_service_account)",
    "    # Load from environment variable (recommended for production)\n    cred_dict = json.loads(firebase_service_account)",
    "Remove duplicate `import json` inside firebase init"
)

print(f"\n{changes} replacements made")

# Restore CRLF and write
output = src.replace('\n', '\r\n')
with open(path, 'wb') as f:
    f.write(output.encode('utf-8'))

# Verify syntax
try:
    tree = ast.parse(src)
    print("Syntax OK")
    bare = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.type is None]
    print(f"Bare excepts in app.py: {bare[:10]}")
except SyntaxError as e:
    print(f"SyntaxError: {e}")
