src = open(r'e:\Users\abhihub\New folder\abhihub\app.py', encoding='utf-8').read()
lines = src.splitlines()
terms = ['resource_landing', 'save_file_record', 'get_all_files_unified', '/resource/']
for term in terms:
    hits = [(i+1, l.strip()) for i, l in enumerate(lines) if term in l]
    print(f'\n=== {term} ({len(hits)} hits) ===')
    for ln, content in hits[:8]:
        print(f'  L{ln}: {content[:90]}')
