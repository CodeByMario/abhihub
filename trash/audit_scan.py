# -*- coding: utf-8 -*-
"""
AbhiHub Codebase Audit Scanner
Produces structured findings for all 7 audit categories.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
import ast, re, os, sys
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))

SCAN_FILES = [
    'app.py',
    'methods/supabase_helper.py',
    'methods/cloudinary_helper.py',
    'methods/search_api.py',
    'methods/storage.py',
    'methods/know_me.py',
    'methods/upload_notifier.py',
    'methods/indexer.py',
]

findings = []  # list of dicts

def add(category, severity, fpath, line, desc, fix):
    findings.append({
        'cat': category,
        'sev': severity,
        'file': fpath,
        'line': line,
        'desc': desc,
        'fix': fix,
    })

# ── SCAN ────────────────────────────────────────────────────────────────────

for rel_path in SCAN_FILES:
    fpath = os.path.join(BASE, rel_path)
    if not os.path.exists(fpath):
        print(f"[SKIP] {rel_path} not found")
        continue

    src = open(fpath, encoding='utf-8').read()
    lines = src.splitlines()

    # ── Try AST parse ────────────────────────────────────────────────────────
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        add('BUG', 'CRITICAL', rel_path, e.lineno, f'SyntaxError: {e.msg}', 'Fix syntax')
        continue

    # Build parent map
    parent_map = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_map[id(child)] = node

    # 1. Bare except
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            add('BUG', 'HIGH', rel_path, node.lineno,
                'Bare except: masks all errors silently',
                'Replace with except Exception as e and log the error')

    # 2. Import inside function
    func_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    mod = child.names[0].name if isinstance(child, ast.Import) else child.module
                    add('DUPE', 'MEDIUM', rel_path, child.lineno,
                        f'Import `{mod}` inside function `{node.name}`',
                        'Move to top-level imports')

    # 3. Duplicate from-imports (same symbol imported multiple times)
    import_counts = defaultdict(list)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            p = parent_map.get(id(node))
            if not isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for alias in node.names:
                    import_counts[alias.name].append(node.lineno)
    for name, lns in import_counts.items():
        if len(lns) > 1:
            add('DUPE', 'LOW', rel_path, lns[0],
                f'Symbol `{name}` imported {len(lns)} times at lines {lns}',
                'Remove duplicate import')

    # ── Line-by-line patterns ────────────────────────────────────────────────
    prev_lines = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # 4. Hardcoded dates / month strings
        if re.search(r"['\"]20\d\d-[01]\d['\"]", line) and 'created_at' not in line.lower():
            add('BUG', 'MEDIUM', rel_path, i,
                f'Hardcoded date string: {stripped[:80]}',
                'Replace with datetime.now().strftime or env variable')

        # 5. Hardcoded admin emails
        if re.search(r"['\"][a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}['\"]", line):
            if 'ADMIN' in line.upper() or 'admin' in line or '@' in line:
                if '#' not in stripped[:20]:
                    add('SEC', 'HIGH', rel_path, i,
                        f'Hardcoded email: {stripped[:80]}',
                        'Move to env variable ADMIN_EMAILS')

        # 6. O(N) linear scan in loop
        if re.search(r'for .+ in .+:\s*$', line):
            next_lines = '\n'.join(lines[i:i+5])
            if 'rank' in next_lines.lower() or 'find' in next_lines.lower():
                add('OPT', 'MEDIUM', rel_path, i,
                    f'Possible O(N) linear scan: {stripped[:80]}',
                    'Convert to dict lookup')

        # 7. Multiple list comprehensions over same var
        if re.search(r'\[.+ for .+ in (\w+)\]', line):
            m = re.search(r'for .+ in (\w+)', line)
            if m:
                varname = m.group(1)
                if any(f'for .+ in {varname}' in prev for prev in prev_lines[-10:]):
                    add('OPT', 'MEDIUM', rel_path, i,
                        f'Repeated iteration over `{varname}`: {stripped[:60]}',
                        'Combine into single pass')

        # 8. TODO / FIXME / HACK
        if re.search(r'#\s*(TODO|FIXME|HACK|XXX)', line, re.IGNORECASE):
            add('BUG', 'LOW', rel_path, i,
                f'Unresolved comment: {stripped[:80]}',
                'Resolve or remove')

        # 9. print() left in production code
        if re.match(r'\s*print\(', line) and 'test' not in rel_path:
            add('OPT', 'LOW', rel_path, i,
                f'print() in production code: {stripped[:60]}',
                'Replace with logging.debug/info')

        # 10. CSRF TIME_LIMIT = None
        if 'CSRF_TIME_LIMIT' in line and 'None' in line:
            add('SEC', 'HIGH', rel_path, i,
                'CSRF TIME_LIMIT set to None — no expiry',
                "Set to 3600 (1 hour)")

        # 11. Unused variable pattern (very rough)
        m = re.match(r'\s*(\w+)\s*=\s*.+', line)
        if m:
            varname = m.group(1)
            if varname not in ('self', '_', '__') and len(varname) > 2:
                rest = '\n'.join(lines[i:min(i+30, len(lines))])
                if varname not in rest and varname + ' ' not in rest:
                    pass  # too noisy without AST scope, skip

        prev_lines.append(line)

    # ── Duplicate block detection (copy-paste) ───────────────────────────────
    # Look for quota/credit check duplicated
    quota_blocks = [i+1 for i, l in enumerate(lines) if '_consume_credit' in l]
    if len(quota_blocks) > 3:
        add('DUPE', 'HIGH', rel_path, quota_blocks[0],
            f'_consume_credit called {len(quota_blocks)} times at lines {quota_blocks[:5]}',
            'Extract to shared decorator or helper')

    save_access_blocks = [i+1 for i, l in enumerate(lines) if 'save_file_access' in l]
    if len(save_access_blocks) > 2:
        add('DUPE', 'MEDIUM', rel_path, save_access_blocks[0],
            f'save_file_access called {len(save_access_blocks)} times inline',
            'Extract to decorator')

    device_detect = [i+1 for i, l in enumerate(lines) if 'user_agent' in l.lower() and ('mobile' in l.lower() or 'device' in l.lower())]
    if len(device_detect) > 1:
        add('DUPE', 'HIGH', rel_path, device_detect[0],
            f'Device detection logic duplicated at {len(device_detect)} locations',
            'Extract to get_device_type() in methods/')


# ── DEAD FILE DETECTION ──────────────────────────────────────────────────────
dead_candidates = [
    'old_store_room.js', 'check2.py', 'check_docs.py',
    'test_stats.py', 'test_supabase.py', 'test_supabase2.py',
    'test_ts.js', 'test_ts2.js', 'test_ts3.js',
    'migrate_data.py', 'migrate_data_and_rank.py', 'migrate_data_json.py',
    'migrate_final_data.py', 'migrate_main_data.py', 'migrate_search_index.py',
    'verify_db.py', 'verify_migration.py', 'replace.py',
    'inspect_db.py', 'generate_vapid.py',
]
for f in dead_candidates:
    fpath = os.path.join(BASE, f)
    if os.path.exists(fpath):
        size = os.path.getsize(fpath)
        add('DEAD', 'LOW', f, 0,
            f'Likely dead file ({size//1024}KB) — one-off script or old code',
            'Confirm and delete or move to /trash')


# ── LIBRARY REPLACEMENT ──────────────────────────────────────────────────────
app_src = open(os.path.join(BASE, 'app.py'), encoding='utf-8').read()
if '_similar' in app_src and '_parse_query' in app_src:
    # find their line numbers
    for i, l in enumerate(app_src.splitlines(), 1):
        if 'def _similar' in l or 'def _parse_query' in l or 'def _tokenize' in l:
            add('LIB', 'MEDIUM', 'app.py', i,
                f'Custom search function `{l.strip()}` — reinventing the wheel',
                'Replace with rapidfuzz or Supabase FTS')

# Check for manual CORS handling vs flask-cors
cors_manual = os.path.exists(os.path.join(BASE, 'cors.py'))
if cors_manual:
    add('LIB', 'LOW', 'cors.py', 0,
        'Manual CORS script exists alongside flask-cors dependency',
        'Confirm flask-cors handles all cases, delete cors.py if redundant')

# ── OUTPUT ───────────────────────────────────────────────────────────────────
import json
sev_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
findings.sort(key=lambda x: (sev_order.get(x['sev'], 9), x['file'], x['line']))

# Write JSON FIRST (before any print that could crash)
out_path = os.path.join(BASE, 'audit_findings.json')
with open(out_path, 'w', encoding='utf-8') as fp:
    json.dump(findings, fp, indent=2)

# Summary
from collections import Counter
cat_counts = Counter(f['cat'] for f in findings)
sev_counts = Counter(f['sev'] for f in findings)
print(f"TOTAL FINDINGS: {len(findings)}")
print(f"By Category: {dict(cat_counts)}")
print(f"By Severity: {dict(sev_counts)}")
print()

# Table - ascii only
print(f"{'#':<4} {'SEV':<9} {'CAT':<8} {'FILE':<35} {'LINE':<6} DESCRIPTION")
print('-'*120)
for idx, f in enumerate(findings, 1):
    desc = f['desc'][:55].encode('ascii', 'replace').decode('ascii')
    ffile = f['file'][:34]
    print(f"{idx:<4} {f['sev']:<9} {f['cat']:<8} {ffile:<35} {str(f['line']):<6} {desc}")

print(f"\nSaved: {out_path}")
