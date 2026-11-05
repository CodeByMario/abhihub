"""
Script to bump the platform version and sync it across version.py and static/sw.js.
Usage:
  python scripts/bump_version.py [patch|minor|major]
  python scripts/bump_version.py 2.0.17
"""
import sys
import re
import os

VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'version.py')
SW_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'sw.js')

def get_current_version():
    with open(VERSION_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
    return m.group(1) if m else "1.0.0"

def bump_semver(v, part='patch'):
    parts = [int(p) for p in v.split('.')]
    while len(parts) < 3:
        parts.append(0)
    if part == 'major':
        parts[0] += 1
        parts[1] = 0
        parts[2] = 0
    elif part == 'minor':
        parts[1] += 1
        parts[2] = 0
    else: # patch
        parts[2] += 1
    return '.'.join(str(p) for p in parts)

def update_version(new_ver):
    # 1. Update version.py
    with open(VERSION_FILE, 'r', encoding='utf-8') as f:
        v_content = f.read()
    v_content = re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', f'APP_VERSION = "{new_ver}"', v_content)
    with open(VERSION_FILE, 'w', encoding='utf-8') as f:
        f.write(v_content)

    # 2. Update static/sw.js
    if os.path.exists(SW_FILE):
        with open(SW_FILE, 'r', encoding='utf-8') as f:
            sw_content = f.read()
        sw_content = re.sub(r"const CACHE_VERSION\s*=\s*['\"]v[^'\"]+['\"];", f"const CACHE_VERSION = 'v{new_ver}';", sw_content)
        with open(SW_FILE, 'w', encoding='utf-8') as f:
            f.write(sw_content)
    print(f"Updated platform version: {new_ver} (synchronized with version.py and static/sw.js)")

if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else 'patch'
    current = get_current_version()
    if arg in ('patch', 'minor', 'major'):
        target = bump_semver(current, arg)
    else:
        target = arg.lstrip('v')
    update_version(target)
