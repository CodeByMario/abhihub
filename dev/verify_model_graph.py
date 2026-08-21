#!/usr/bin/env python3
"""
Model Relation Graph Updater — scans the project for schema/model/route changes
and prints what needs to be updated in DATA_MODEL_RELATIONS.md.

Run after any agent change to verify the relation graph is still accurate.
"""

import re
import os
import sys
from pathlib import Path

ROOT = Path.cwd().resolve()

def read_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""

def find_migrations():
    mig_dir = ROOT / "migrations"
    if not mig_dir.is_dir():
        return []
    return sorted(mig_dir.glob("*.sql"), key=lambda p: p.name)

def find_tables_in_migrations():
    tables = []
    for sql_file in find_migrations():
        content = read_file(sql_file)
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+(\S+\.\S+)", content):
            fqn = m.group(1)
            table = fqn.split(".")[-1]
            tables.append((table, f"migrations/{sql_file.name}", "CREATE TABLE"))
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+(\S+)\s*\(", content):
            table = m.group(1)
            if "." not in table and table.upper() not in ("TRUE", "FALSE", "NULL"):
                tables.append((table, f"migrations/{sql_file.name}", "CREATE TABLE"))
    return tables

def find_model_files():
    models = []
    data_dir = ROOT / "data"
    if not data_dir.is_dir():
        return models
    for py_file in data_dir.glob("*.py"):
        content = read_file(py_file)
        name = py_file.stem
        table_match = re.search(r"TABLE\s*=\s*[\"']([^\"']+)[\"']", content)
        table = table_match.group(1) if table_match else "?"
        models.append((name, table, f"data/{py_file.name}"))
    return models

def find_indexes_in_migrations():
    indexes = []
    for sql_file in find_migrations():
        content = read_file(sql_file)
        for m in re.finditer(r"CREATE\s+(UNIQUE\s+)?INDEX\s+IF NOT EXISTS\s+(\S+)", content):
            unique = bool(m.group(1))
            index_name = m.group(2)
            rest = content[m.end():m.end()+300]
            on_match = re.search(r"ON\s+(\S+)\s*\(", rest)
            table = on_match.group(1) if on_match else "?"
            source = f"migrations/{sql_file.name}"
            indexes.append((index_name, table, "UNIQUE" if unique else "", source))
    return indexes

def find_views_in_migrations():
    views = []
    for sql_file in find_migrations():
        content = read_file(sql_file)
        for m in re.finditer(r"CREATE\s+(OR\s+REPLACE\s+)?(VIEW\s+)?(\S+)\s+AS", content):
            view_name = m.group(3)
            views.append((view_name, f"migrations/{sql_file.name}"))
    return views

def find_foreign_keys():
    fks = []
    for sql_file in find_migrations():
        content = read_file(sql_file)
        for m in re.finditer(r"REFERENCES\s+(\S+\.)?(\S+)", content):
            schema = m.group(1) or ""
            table = m.group(2)
            ctx_start = max(0, m.start() - 80)
            ctx = content[ctx_start:m.start()]
            col_match = re.search(r"(\w+)\s+\w+\s+REFERENCES", ctx)
            col = col_match.group(1) if col_match else "?"
            fks.append((col, table, f"migrations/{sql_file.name}"))
    return fks

def find_table_references_in_python():
    refs = {}
    for pattern in ["methods/**/*.py", "data/*.py", "app.py"]:
        for py_file in ROOT.glob(pattern):
            if not py_file.is_file():
                continue
            content = read_file(py_file)
            rel_path = str(py_file.relative_to(ROOT))
            for m in re.finditer(r"\.table\(['\"](\S+)['\"]", content):
                table = m.group(1)
                line_num = content[:m.start()].count("\n") + 1
                key = table
                if key not in refs:
                    refs[key] = []
                refs[key].append(f"  → {rel_path}:{line_num}")
    return refs

def find_tables_in_routes_md():
    """Find table references in ROUTES.md section 10.1"""
    routes_md = ROOT / "docs" / "reference" / "ROUTES.md"
    if not routes_md.is_file():
        return []
    content = read_file(routes_md)
    tables = []
    for m in re.finditer(r"\|\s+`(\w+)`\s+\|\s+(SELECT|INSERT|UPDATE|DELETE|SELECT,\s*INSERT)\s+\|", content):
        tables.append(m.group(1))
    return tables

def main():
    print("=" * 70)
    print("AbhiHub — Model Relation Graph Verification")
    print("=" * 70)
    print(f"Root: {ROOT}")
    print()

    migrations = find_migrations()
    print(f"📦 Migrations ({len(migrations)}):")
    for m in migrations:
        print(f"   {m.name}")
    print()

    tables = find_tables_in_migrations()
    print(f"📋 Tables in migrations ({len(tables)}):")
    for table, source, stmt in tables:
        print(f"   {table:25s} ({source})")
    print()

    models = find_model_files()
    print(f"📋 Model files ({len(models)}):")
    for name, table, path in models:
        print(f"   {name:20s} → TABLE={table:25s} ({path})")
    print()

    indexes = find_indexes_in_migrations()
    print(f"🔍 Indexes ({len(indexes)}):")
    for name, table, unique, source in indexes:
        flag = f"[{unique}] " if unique else ""
        print(f"   {flag}{name:40s} ON {table:25s} ({source})")
    print()

    views = find_views_in_migrations()
    print(f"👁️  Views ({len(views)}):")
    for name, source in views:
        print(f"   {name:40s} ({source})")
    print()

    fks = find_foreign_keys()
    print(f"🔗 Foreign Keys ({len(fks)}):")
    for col, table, source in fks:
        print(f"   {col:25s} → {table:25s} ({source})")
    print()

    table_refs = find_table_references_in_python()
    print(f"📡 Python .table() references ({len(table_refs)} unique tables):")
    for table in sorted(table_refs.keys()):
        print(f"   {table}")
        for ref in table_refs[table]:
            print(ref)
    print()

    routes_tables = find_tables_in_routes_md()
    print(f"📑 Tables listed in ROUTES.md §10.1 ({len(routes_tables)}):")
    for t in routes_tables:
        print(f"   {t}")
    print()

    print("=" * 70)
    print("✅ Run this after every agent change to verify DATA_MODEL_RELATIONS.md")
    print("=" * 70)

if __name__ == "__main__":
    main()
