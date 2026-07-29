import os
import re

base_dir = r'e:\Users\abhihub\New folder\abhihub\templates'
injected_count = 0

for root, _, files in os.walk(base_dir):
    for file in files:
        if file.endswith('.html'):
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find all <form> tags that don't already have csrf_token
            # Simple approach: inject inside <form ...>
            if '<form' in content.lower() and 'csrf_token' not in content:
                # Regex to match <form ...> and append the hidden input
                new_content = re.sub(
                    r'(<form[^>]*>)',
                    r'\1\n    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>',
                    content,
                    flags=re.IGNORECASE
                )
                
                if new_content != content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    injected_count += 1
                    print(f"Injected CSRF token into {file}")

print(f"Total files injected: {injected_count}")
