import ast, re, json

path = r'e:\Users\abhihub\New folder\abhihub\app.py'
src = open(path, encoding='utf-8').read()
lines = src.splitlines()

# Find all @app.route decorators
routes = []
for i, line in enumerate(lines):
    if '@app.route(' in line:
        m = re.search(r"@app\.route\([\"'](.*?)[\"']", line)
        meth = re.search(r"methods=\[(.*?)\]", line)
        if m:
            route = m.group(1)
            methods = meth.group(1).replace('"','').replace("'",'').strip() if meth else 'GET'
            routes.append({'route': route, 'methods': methods, 'line': i+1})

# AST: get function bounds
tree = ast.parse(src)
func_bounds = []
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        func_bounds.append((node.lineno, node.end_lineno, node.name))
func_bounds.sort()

def get_func_for_line(lineno):
    for start, end, name in func_bounds:
        if lineno <= start <= lineno + 5:
            return start, end, name
    return None, None, None

DB_PATTERNS = [
    r'\.table\(',
    r'supabase\.table\(',
    r'client\.table\(',
    r'supabase\.auth\.',
    r'from methods\.supabase_helper import',
    r'get_all_files_merged|get_all_file_records|get_student_profile|get_user_uploaded|calculate_user_ranks|get_reputation|get_contribution|get_all_colleges|get_all_branches|search_file_records|save_file_record|get_pending|get_leaderboard|load_subscriptions|get_user_file_history|get_all_notifications|get_document_by',
]

results = []
for r in routes:
    start, end, fname = get_func_for_line(r['line'])
    if not start:
        continue
    body_lines = lines[start-1:end]
    
    db_calls = []
    for j, bl in enumerate(body_lines):
        for pat in DB_PATTERNS:
            if re.search(pat, bl):
                db_calls.append(f'L{start+j}: {bl.strip()[:80]}')
                break
    
    results.append({
        'route': r['route'],
        'methods': r['methods'],
        'func': fname,
        'line': r['line'],
        'db_count': len(db_calls),
        'calls': db_calls
    })

results.sort(key=lambda x: -x['db_count'])

print(f'Total routes analyzed: {len(results)}')
print()
for r in results:
    if r['db_count'] > 0:
        tag = 'HIGH' if r['db_count'] >= 5 else ('MED' if r['db_count'] >= 3 else 'LOW')
        print(f'[{tag}][{r["db_count"]:2d}] {r["methods"]:<18} {r["route"]:<45} fn={r["func"]}')
        for c in r['calls'][:6]:
            print(f'          {c}')
        if len(r['calls']) > 6:
            print(f'          ... +{len(r["calls"])-6} more')
        print()

with open('api_call_analysis.json', 'w') as f:
    json.dump(results, f, indent=2)
print(f'Saved api_call_analysis.json')
