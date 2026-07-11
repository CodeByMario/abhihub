import os
import re
import ast

base_dir = r'e:\Users\abhihub\New folder\abhihub'

patterns = {
    'DB_STRING_FORMATTING': (r'\.execute\(f[\'"].*?\{.*?\}', 'Possible SQL Injection via string formatting in execute()'),
    'OPEN_REDIRECT': (r'redirect\(\s*request\.args\.get\([\'"]next[\'"]', 'Open Redirect vulnerability via unvalidated next parameter'),
    'MASS_ASSIGNMENT': (r'\.update\(request\.(?:json|form)\)', 'Mass Assignment risk in DB update'),
    'CORS_WILDCARD': (r'CORS\(.*origins=[\'"]\*[\'"]', 'CORS allows all origins'),
    'DEBUG_MODE_ON': (r'app\.run\(.*debug=True', 'Debug mode is explicitly set to True'),
    'WEAK_SECRET': (r'app\.secret_key\s*=\s*[\'"][^\'"]+[\'"]', 'Hardcoded Flask Secret Key'),
    'API_KEY_LEAK': (r'(?i)API_KEY\s*=\s*[\'"][^\'"]+[\'"]', 'Hardcoded API Key'),
    'JWT_SECRET_LEAK': (r'(?i)JWT_SECRET\s*=\s*[\'"][^\'"]+[\'"]', 'Hardcoded JWT Secret'),
}

findings = []

def check_file(path, file):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.splitlines()
            
            # Regex checks
            for i, line in enumerate(lines):
                for key, (pattern, desc) in patterns.items():
                    if re.search(pattern, line):
                        # Filter false positives
                        if key == 'WEAK_SECRET' and 'os.getenv' in line: continue
                        findings.append(f"[{key}] {file}:{i+1} -> {desc}\n    {line.strip()[:80]}")
                        
            # AST checks for Python files
            if file.endswith('.py'):
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    # Check for routes without auth
                    if isinstance(node, ast.FunctionDef):
                        is_route = any(isinstance(d, ast.Call) and getattr(d.func, 'attr', '') == 'route' for d in node.decorator_list)
                        if is_route:
                            route_path = ""
                            for d in node.decorator_list:
                                if isinstance(d, ast.Call) and getattr(d.func, 'attr', '') == 'route' and d.args:
                                    if isinstance(d.args[0], ast.Constant):
                                        route_path = d.args[0].value
                            
                            has_auth = any(getattr(d, 'id', '') in ['auth_required', 'admin_required'] for d in node.decorator_list)
                            
                            sensitive_paths = ['/admin', '/delete', '/update', '/settings', '/account', 'api/admin']
                            if route_path and not has_auth and any(s in route_path for s in sensitive_paths):
                                if 'login' not in route_path and 'reset' not in route_path:
                                    findings.append(f"[MISSING_AUTH] {file}:{node.lineno} -> Route '{route_path}' might require authentication\n    def {node.name}(...)")
                                    
    except Exception as e:
        pass

for root, dirs, files in os.walk(base_dir):
    if any(x in root for x in ['node_modules', '.git', 'trash', 'venv', '__pycache__']):
        continue
    for file in files:
        if file.endswith(('.py', '.js', '.html')):
            check_file(os.path.join(root, file), file)

if not findings:
    print("No high-risk patterns found.")
else:
    for f in findings:
        print(f)
