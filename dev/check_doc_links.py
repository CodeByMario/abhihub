"""
Validate relative markdown links in the curated docs.

Checks README.md, CONTRIBUTING.md, SECURITY.md, CHANGELOG.md and
everything under docs/. Skips http(s) links and anchors.
Exits 1 if any target is missing.
"""

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

files = ["README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md"]
for dp, dn, fn in os.walk("docs"):
    dn[:] = [d for d in dn if d not in ("__pycache__",)]
    for f in fn:
        if f.endswith(".md"):
            files.append(os.path.join(dp, f))

broken = []
checked = 0
for path in files:
    if not os.path.exists(path):
        continue
    base = os.path.dirname(path)
    text = open(path, encoding="utf-8", errors="ignore").read()
    for m in LINK.finditer(text):
        target = m.group(1).strip()
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        target = target.split("#")[0]
        if not target:
            continue
        resolved = os.path.normpath(os.path.join(base, target))
        checked += 1
        if not os.path.exists(resolved):
            broken.append((path.replace(os.sep, "/"), target,
                           resolved.replace(os.sep, "/")))

print("links checked: %d" % checked)
if broken:
    print("\nBROKEN (%d):" % len(broken))
    for src, target, resolved in broken:
        print("  %s" % src)
        print("      -> %s   (resolves to %s)" % (target, resolved))
    sys.exit(1)
print("RESULT: PASS — all relative links resolve")
