import json
from collections import Counter

data = json.load(open('audit_findings.json', encoding='utf-8'))
cat_counts = Counter(f['cat'] for f in data)
sev_counts = Counter(f['sev'] for f in data)
print(f'TOTAL: {len(data)}')
print(f'By Category: {dict(cat_counts)}')
print(f'By Severity: {dict(sev_counts)}')
print()
high = [f for f in data if f['sev'] in ('CRITICAL', 'HIGH')]
print(f'--- HIGH/CRITICAL ({len(high)}) ---')
for f in high:
    print(f"  [{f['sev']}][{f['cat']}] {f['file']}:{f['line']} - {f['desc'][:70]}")
