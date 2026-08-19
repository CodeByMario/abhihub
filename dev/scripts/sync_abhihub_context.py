#!/usr/bin/env python3
"""
sync_abhihub_context.py — Build live AbhiHub context for the Instagram automation.

Queries the live DB (abhihub schema) for the top contributor by upload count,
plus the brand share link, and writes abhihub_context.json that the
instagram-automation project consumes (to feature real students as social proof
and embed a referral share link in posts).

Output location: set ABHIHUB_CONTEXT_OUT to the instagram-automation folder,
or it defaults to <repo>/exports/abhihub_context.json.
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _load_env():
    p = os.path.join(ROOT, '.env')
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    _load_env()
    from methods.supabase_helper import init_supabase
    c = init_supabase()
    if not c:
        print("Supabase unavailable")
        return
    # Top uploader by documents count (anon key can read documents)
    r = c.table('documents').select('uploader_id').execute()
    counts = {}
    for row in (r.data or []):
        uid = row.get('uploader_id')
        if uid:
            counts[uid] = counts.get(uid, 0) + 1
    top_id = max(counts, key=counts.get) if counts else None

    topper_name = "a top AbhiHub contributor"
    if top_id:
        try:
            pr = c.table('profiles').select('full_name').eq('id', top_id).limit(1).execute()
            if pr.data:
                topper_name = pr.data[0].get('full_name') or topper_name
        except Exception:
            pass

    ctx = {
        "topper_name": topper_name,
        "branch": "",
        "exam_name": "Semester-end PYQ & notes pack",
        "share_url": f"https://abhihub.edu.eu.org/u/{top_id}" if top_id else "https://abhihub.edu.eu.org/pyq",
    }
    out = os.getenv('ABHIHUB_CONTEXT_OUT') or os.path.join(ROOT, 'exports', 'abhihub_context.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(ctx, f, ensure_ascii=False, indent=2)
    print(f"Wrote context -> {out}")
    print(f"  topper: {topper_name} (uploads={counts.get(top_id,0)})")
    print(f"  share_url: {ctx['share_url']}")


if __name__ == '__main__':
    main()
