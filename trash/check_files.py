import ast

path = r'e:\Users\abhihub\New folder\abhihub\app.py'
raw = open(path, 'rb').read()
src = raw.decode('utf-8').replace('\r\n', '\n')

# I need to find the `resource_landing` function and change how it gets related files.
# But actually, I looked at resource_landing earlier, and it DOES NOT use `get_all_files_unified()`.
# The pyq route does, and we didn't touch it. But load_data() uses get_all_files_unified().
# Wait, let me double check where `get_all_files_unified()` is used.

# Let's search again to make sure.
lines = src.splitlines()
for i, l in enumerate(lines):
    if 'get_all_files_unified' in l:
        print(f"L{i+1}: {l}")

