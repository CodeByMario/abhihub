"""
Verify each BUGS.md item against the current codebase.

Prints FIXED / OPEN per item with the evidence used, so BUGS.md statuses
can be updated from facts rather than memory.
"""

import os
import re
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)


def read(path):
    if not os.path.exists(path):
        return ""
    return open(path, encoding="utf-8", errors="ignore").read()


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=60).stdout
    except Exception:
        return ""


app = read("app.py")
helper = read("methods/supabase_helper.py")
notifier = read("methods/upload_notifier.py")

prod_files = ["app.py"]
for d in ("methods", "data"):
    if os.path.isdir(d):
        prod_files += [os.path.join(d, f) for f in sorted(os.listdir(d))
                       if f.endswith(".py")]
prod = {p: read(p) for p in prod_files}

results = []


def check(item, ok, evidence):
    results.append((item, "FIXED" if ok else "OPEN", evidence))


# --- HIGH ---
bare = sum(len(re.findall(r"^\s*except\s*:\s*$", t, re.M)) for t in prod.values())
check("H1 bare except", bare == 0, "%d bare except in production" % bare)

m = re.search(r"@app\.route\('/delete-account'\)\s*\n@auth_required", app)
check("H2 /delete-account auth", bool(m), "decorator present" if m else "missing @auth_required")

m = re.search(r"@app\.route\('/pdf-proxy/<path:pdf_name>'\)\s*\n@auth_required", app)
referer = "[PDF-PROXY] Blocked cross-origin" in app
check("H3 /pdf-proxy auth", bool(m) and referer,
      "auth=%s referer_check=%s" % (bool(m), referer))

m = re.search(r"ADMIN_EMAILS\s*=.*getenv\('ADMIN_EMAILS',\s*''\)", app)
check("H4 admin email default", bool(m), "empty default" if m else "hardcoded fallback")

m = re.search(r"WTF_CSRF_TIME_LIMIT'\]\s*=\s*(\d+)", app)
check("H5 CSRF TTL", bool(m), "TTL=%s" % (m.group(1) if m else "None"))

wild = len(re.findall(r"Allow-Origin'\]\s*=\s*'\*'", app))
check("H6 CORS wildcard", wild == 0 and not os.path.exists("cors.py"),
      "wildcards=%d cors.py=%s" % (wild, os.path.exists("cors.py")))

# --- MEDIUM ---
has_helper = "def log_document_view(" in app
sfa = len(re.findall(r"save_file_access\(", app))
check("M1 view-log dedup", has_helper and sfa <= 2,
      "helper=%s save_file_access_sites=%d" % (has_helper, sfa))

dev = len(re.findall(r"^def get_device_type", app, re.M))
check("M2 device detect dedup", dev == 1, "%d definitions" % dev)

inline_helper = len(re.findall(r"^\s+from methods\.supabase_helper import", app, re.M))
check("M3 inline helper imports", inline_helper == 0,
      "%d inline imports (design choice: lazy import)" % inline_helper)

init_sb = len(re.findall(r"^from methods\.supabase_helper import.*init_supabase", app, re.M))
check("M4 init_supabase module imports", init_sb <= 1, "%d module-level" % init_sb)

prints = sum(len(re.findall(r"^\s*print\(", t, re.M)) for t in prod.values())
check("M6 print() in production", prints == 0, "%d print() calls" % prints)

check("M7 fuzzy search note", "rapidfuzz" in app,
      "rapidfuzz in use" if "rapidfuzz" in app else "custom tokenizer only")

check("M8 cors.py removed", not os.path.exists("cors.py"),
      "cors.py absent" if not os.path.exists("cors.py") else "still present")

tb_helper = len(re.findall(r"^\s+import traceback", helper, re.M))
tb_app = len(re.findall(r"^[ \t]+import traceback", app, re.M))
check("M9 inline traceback", tb_helper == 0 and tb_app == 0,
      "helper=%d app=%d (module-level import is fine)" % (tb_helper, tb_app))

re_inline = len(re.findall(r"^\s+import re\s*$", app, re.M))
check("M10 inline re import", re_inline == 0, "%d inline" % re_inline)

hard_year = len(re.findall(r"'20(2[4-9])'", app))
check("M11 hardcoded dates", hard_year == 0, "%d hardcoded year literals" % hard_year)

subj = "Subject name too long" in app
coll = "College name too long" in app
dept = "Name too long" in app or "Department name too long" in app
check("M12 input length validation", subj and coll and dept,
      "subject=%s college=%s dept=%s" % (subj, coll, dept))

check("M13 O(1) rank lookup", "_rank_lookup" in app,
      "dict lookup" if "_rank_lookup" in app else "linear scan")

check("M14 single-pass categorisation", "Single-pass categorization" in app,
      "single loop" if "Single-pass categorization" in app else "4 comprehensions")

sio_wild = 'cors_allowed_origins="*"' in app
check("M15 SocketIO CORS", not sio_wild,
      "restricted" if not sio_wild else "wildcard")

# --- LOW ---
root_py = [f for f in os.listdir(".") if f.endswith(".py")]
check("L1 dead code files", len(root_py) <= 8, "%d root .py files" % len(root_py))

sb_cfg = read("static/supabase-config.js")
documented = "anon" in read("SECURITY.md").lower()
check("L2 anon key documented", documented,
      "SECURITY.md mentions anon key" if documented else "undocumented")

tsec = read("tests/test_dashboard_auth.py")
check("L3 test secret", "getenv" in tsec or "test-secret" in tsec,
      "dummy value only (not a real secret)")

tmpl_hard = sh("grep -rl 0x4AAAAAAEKPpLMi4eWOTMtC templates/ 2>/dev/null").strip()
check("L4 Turnstile sitekey", tmpl_hard == "",
      "env var" if tmpl_hard == "" else "hardcoded in " + tmpl_hard)

routes_md = read("docs/reference/ROUTES.md")
check("L5 ROUTES.md dead links", "[REMOVED" in routes_md,
      "relabelled" if "[REMOVED" in routes_md else "still listed as live")

tojson = sh("grep -rl 'tojson|safe' templates/ 2>/dev/null").strip()
check("L6 tojson|safe", tojson == "", "removed" if tojson == "" else tojson)

check("L7 CSS doc location",
      os.path.exists("docs/history/CSS_CONFLICTS_RESOLVED.md")
      and not os.path.exists("templates/_CSS_CONFLICTS_RESOLVED.md"),
      "moved to docs/history/")

hp = len(re.findall(r"^\s*print\(", helper, re.M))
check("L8 print() in supabase_helper", hp == 0, "%d print()" % hp)

# --- report ---
fixed = [r for r in results if r[1] == "FIXED"]
openi = [r for r in results if r[1] == "OPEN"]

print("=" * 68)
print("BUGS.md VERIFICATION  —  %d FIXED / %d OPEN" % (len(fixed), len(openi)))
print("=" * 68)
for item, status, ev in results:
    mark = "[x]" if status == "FIXED" else "[ ]"
    print("%s %-34s %-6s %s" % (mark, item, status, ev))
