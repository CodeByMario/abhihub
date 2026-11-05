"""
Patch app.py to respect WTF_CSRF_ENABLED in before_request check_csrf.
"""
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = """@app.before_request
def check_csrf():
    if request.method not in ['GET', 'HEAD', 'OPTIONS', 'TRACE']:
        if request.path.startswith('/api/') or request.path.startswith('/auth') or request.path.startswith('/store-room/api/'):
            return
        csrf.protect()"""

replacement = """@app.before_request
def check_csrf():
    if not app.config.get('WTF_CSRF_ENABLED', True):
        return
    if request.method not in ['GET', 'HEAD', 'OPTIONS', 'TRACE']:
        if request.path.startswith('/api/') or request.path.startswith('/auth') or request.path.startswith('/store-room/api/'):
            return
        csrf.protect()"""

if target in content:
    content = content.replace(target, replacement, 1)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched check_csrf in app.py")
else:
    print("Target not found in app.py")
