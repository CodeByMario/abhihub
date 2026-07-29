import ast

path = r'e:\Users\abhihub\New folder\abhihub\app.py'
raw = open(path, 'rb').read()
app = raw.decode('utf-8').replace('\r\n', '\n')

old_code = """app.secret_key = os.getenv('SECRET_KEY', 'AbhijeetAbhijeet')
app.config['WTF_CSRF_TIME_LIMIT'] = 3600"""

new_code = """app.secret_key = os.getenv('SECRET_KEY', 'AbhijeetAbhijeet')
app.config['WTF_CSRF_TIME_LIMIT'] = 3600

# CSRF Protection Configuration
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)

# Disable default check so we can exempt API routes safely without annotating all 20 of them
app.config['WTF_CSRF_CHECK_DEFAULT'] = False

@app.before_request
def check_csrf():
    if request.method not in ['GET', 'HEAD', 'OPTIONS', 'TRACE']:
        # Exempt API and Auth routes from strict CSRF to prevent breaking React/Fetch calls
        if request.path.startswith('/api/') or request.path.startswith('/auth') or request.path.startswith('/store-room/api/'):
            return
        csrf.protect()
"""

if old_code in app:
    new_src = app.replace(old_code, new_code)
    try:
        ast.parse(new_src)
        print('Syntax OK')
        output = new_src.replace('\n', '\r\n')
        open(path, 'wb').write(output.encode('utf-8'))
        print('Updated app.py successfully with CSRF protection')
    except SyntaxError as e:
        print(f'SyntaxError: {e}')
else:
    print('Error: old_code not found in app.py')
