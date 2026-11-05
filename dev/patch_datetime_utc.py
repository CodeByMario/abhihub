"""
Fix deprecated datetime.utcnow() with timezone-aware datetime.now(timezone.utc)
"""
import os

files_to_patch = [
    os.path.join('methods', 'analytics_reporter.py'),
    os.path.join('methods', 'analytics_tracker.py'),
    os.path.join('methods', 'encrypted_chat.py'),
    os.path.join('methods', 'upload_notifier.py'),
]

for path in files_to_patch:
    if not os.path.exists(path):
        continue
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Ensure timezone is imported from datetime
    if 'datetime.utcnow()' in content:
        # Check imports
        if 'from datetime import' in content:
            if 'timezone' not in content:
                content = content.replace('from datetime import datetime', 'from datetime import datetime, timezone')
                content = content.replace('from datetime import datetime, timedelta', 'from datetime import datetime, timedelta, timezone')
        elif 'import datetime' in content and 'timezone' not in content:
            content = content.replace('import datetime', 'import datetime\nfrom datetime import timezone')

        content = content.replace('datetime.utcnow()', 'datetime.now(timezone.utc)')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Patched datetime in {path}")
