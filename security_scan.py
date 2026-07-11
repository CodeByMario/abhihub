import os
import re
import json

base_dir = r'e:\Users\abhihub\New folder\abhihub'

# Regex patterns for vulnerabilities
patterns = {
    'XSS_JINJA_SAFE': r'\{\{.*\|safe.*?\}\}',
    'RAW_SQL': r'\.execute\(\s*[\"\'].*?select|insert|update|delete.*?[\"\']\s*\)', # basic check, mostly supabase uses ORM though
    'PATH_TRAVERSAL': r'open\([^,]+,\s*[\'"]w[\'"]\)|send_file\(|send_from_directory\(',
    'MISSING_AUTH_ROUTE': r'@app\.route\([^\)]+\)\s*\n\s*(?!@auth_required)def ',
    'NO_CSRF_IN_FORM': r'<form(?!.*csrf_token)',
    'EVAL_EXEC': r'\beval\(|\bexec\(',
    'HARDCODED_SECRETS': r'(?i)(password|secret|key|token)[\s]*=[\s]*[\'"][^\'"]+[\'"]'
}

findings = {k: [] for k in patterns}

for root, dirs, files in os.walk(base_dir):
    if 'node_modules' in root or '.git' in root or 'trash' in root or 'venv' in root:
        continue
        
    for file in files:
        if not file.endswith(('.py', '.html', '.js')):
            continue
            
        path = os.path.join(root, file)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Line by line for precise reporting
            lines = content.splitlines()
            for i, line in enumerate(lines):
                for key, pattern in patterns.items():
                    # Simplified auth check for python only
                    if key == 'MISSING_AUTH_ROUTE' and not file.endswith('.py'):
                        continue
                    if key == 'NO_CSRF_IN_FORM' and not file.endswith('.html'):
                        continue
                    if key == 'XSS_JINJA_SAFE' and not file.endswith('.html'):
                        continue
                        
                    if re.search(pattern, line):
                        # Filter out expected false positives like 'SECRET_KEY = os.getenv...'
                        if key == 'HARDCODED_SECRETS' and 'os.getenv' in line:
                            continue
                        # Basic naive form check
                        if key == 'NO_CSRF_IN_FORM' and '<form' in line.lower() and 'csrf' not in content:
                            findings[key].append(f"{file}:{i+1}")
                        elif key != 'NO_CSRF_IN_FORM':
                            findings[key].append(f"{file}:{i+1} -> {line.strip()[:60]}")
                            
        except Exception as e:
            pass

# Output findings
for key, items in findings.items():
    print(f"=== {key} ({len(items)} hits) ===")
    for item in items[:10]:
        print(f"  {item}")
    if len(items) > 10:
        print(f"  ... +{len(items)-10} more")
    print()
