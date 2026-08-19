#!/usr/bin/env python3
"""
Route parity harness.

WHY: app.py holds every HTTP route. Any refactor that moves routes into
modules must reproduce the EXACT same URL rule set. This script snapshots
the rules and later verifies them, so a refactor can never silently drop
an endpoint (which would 404 in production).

USAGE
    python dev/route_parity.py snapshot   # write baseline
    python dev/route_parity.py verify     # compare current app to baseline

It parses app.py statically (no imports, no env vars, no DB) so it runs
anywhere — including CI and this Windows box where flask_socketio is
broken for py3.13.
"""

from __future__ import annotations

import ast
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join(REPO, "dev", "route_snapshot.json")


def _decorator_route(dec: ast.expr) -> tuple[str, list[str]] | None:
    """Return (rule, methods) if `dec` is an @<something>.route(...) call."""
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if not isinstance(func, ast.Attribute) or func.attr != "route":
        return None
    if not dec.args:
        return None
    first = dec.args[0]
    if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
        return None
    rule = first.value

    methods = ["GET"]
    for kw in dec.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
            found = [
                e.value
                for e in kw.value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            if found:
                methods = found
    return rule, sorted({m.upper() for m in methods})


def collect(paths: list[str]) -> dict[str, dict]:
    """Walk each file and collect every route decorator found."""
    out: dict[str, dict] = {}
    for path in paths:
        if not os.path.exists(path):
            continue
        tree = ast.parse(open(path, encoding="utf-8", errors="ignore").read())
        rel = os.path.relpath(path, REPO).replace("\\", "/")
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                parsed = _decorator_route(dec)
                if not parsed:
                    continue
                rule, methods = parsed
                entry = out.setdefault(
                    rule, {"methods": set(), "handlers": set(), "files": set()}
                )
                entry["methods"].update(methods)
                entry["handlers"].add(node.name)
                entry["files"].add(rel)
    # make JSON-serializable + stable
    return {
        rule: {
            "methods": sorted(v["methods"]),
            "handlers": sorted(v["handlers"]),
            "files": sorted(v["files"]),
        }
        for rule, v in sorted(out.items())
    }


def source_files() -> list[str]:
    """Files that may declare routes: app.py plus any app/ package modules."""
    files = [os.path.join(REPO, "app.py")]
    pkg = os.path.join(REPO, "app")
    if os.path.isdir(pkg):
        for fn in sorted(os.listdir(pkg)):
            if fn.endswith(".py"):
                files.append(os.path.join(pkg, fn))
    wsgi = os.path.join(REPO, "wsgi.py")
    if os.path.exists(wsgi):
        files.append(wsgi)
    return files


def cmd_snapshot() -> int:
    routes = collect(source_files())
    os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
    with open(SNAPSHOT, "w", encoding="utf-8") as fh:
        json.dump(routes, fh, indent=2, sort_keys=True)
    print(f"snapshot written: {SNAPSHOT}")
    print(f"routes captured : {len(routes)}")
    return 0


def cmd_verify() -> int:
    if not os.path.exists(SNAPSHOT):
        print("no snapshot — run: python dev/route_parity.py snapshot")
        return 2
    baseline = json.load(open(SNAPSHOT, encoding="utf-8"))
    current = collect(source_files())

    missing = sorted(set(baseline) - set(current))
    added = sorted(set(current) - set(baseline))
    changed = [
        r
        for r in sorted(set(baseline) & set(current))
        if baseline[r]["methods"] != current[r]["methods"]
    ]

    print(f"baseline routes: {len(baseline)}")
    print(f"current  routes: {len(current)}")

    if missing:
        print(f"\nMISSING ({len(missing)}) — these would 404 in production:")
        for r in missing:
            print(f"  {r}  (was in {', '.join(baseline[r]['files'])})")
    if changed:
        print(f"\nMETHOD CHANGES ({len(changed)}):")
        for r in changed:
            print(f"  {r}: {baseline[r]['methods']} -> {current[r]['methods']}")
    if added:
        print(f"\nADDED ({len(added)}) — informational:")
        for r in added:
            print(f"  {r}")

    if missing or changed:
        print("\nRESULT: FAIL")
        return 1
    print("\nRESULT: PASS — no route lost")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if cmd == "snapshot":
        return cmd_snapshot()
    if cmd == "verify":
        return cmd_verify()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
