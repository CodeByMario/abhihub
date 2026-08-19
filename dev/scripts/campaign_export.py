#!/usr/bin/env python3
"""
campaign_export.py — Segment AbhiHub users from Supabase for growth campaigns.

Outputs CSV(s) to ./exports/ for use by exam_pack_drip.py or manual sends.

Segments:
  active      — last_active_at within --active-days (default 30)
  dormant     — account older than --active-days but no recent activity
  new         — created_at within --new-days (default 14)
  referred    — referred_by is not null (came via referral)
  organic     — referred_by is null

Usage:
  python dev/scripts/campaign_export.py --all
  python dev/scripts/campaign_export.py --segment dormant,new
  python dev/scripts/campaign_export.py --active-days 30 --new-days 14 --outdir exports
"""
import argparse
import csv
import os
import sys
import urllib.request
import json
from datetime import datetime, timezone, timedelta

# ---- config from .env ----
def _load_env():
    vals = {}
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals

ENV = _load_env()
SUPABASE_URL = ENV.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = ENV.get('SUPABASE_KEY', '')
SCHEMA = 'abhihub'

def _req(path, params=''):
    url = f"{SUPABASE_URL}/rest/v1/{path}{params}"
    req = urllib.request.Request(url)
    req.add_header('apikey', SUPABASE_KEY)
    req.add_header('Authorization', 'Bearer ' + SUPABASE_KEY)
    req.add_header('Accept-Profile', SCHEMA)
    req.add_header('Content-Profile', SCHEMA)
    req.add_header('Accept', 'application/json')
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def fetch_all():
    rows = _req('profiles',
                '?select=id,email,full_name,college_id,referral_code,referred_by,'
                'created_at,last_active_at,welcome_seen&limit=1000')
    return rows

def parse_ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace('Z', '+00:00'))
    except Exception:
        return None

def build_segments(rows, active_days, new_days):
    now = datetime.now(timezone.utc)
    segs = {'active': [], 'dormant': [], 'new': [], 'referred': [], 'organic': []}
    for r in rows:
        la = parse_ts(r.get('last_active_at'))
        ca = parse_ts(r.get('created_at'))
        is_active = la and (now - la) <= timedelta(days=active_days)
        is_new = ca and (now - ca) <= timedelta(days=new_days)
        is_referred = bool(r.get('referred_by'))
        if is_active:
            segs['active'].append(r)
        else:
            segs['dormant'].append(r)
        if is_new:
            segs['new'].append(r)
        (segs['referred'] if is_referred else segs['organic']).append(r)
    return segs

def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = ['id', 'email', 'full_name', 'referral_code', 'referred_by',
            'created_at', 'last_active_at']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in cols})
    return len(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true', help='export all segments')
    ap.add_argument('--segment', default='', help='comma list: active,dormant,new,referred,organic')
    ap.add_argument('--active-days', type=int, default=30)
    ap.add_argument('--new-days', type=int, default=14)
    ap.add_argument('--outdir', default='exports')
    args = ap.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print('ERROR: SUPABASE_URL / SUPABASE_KEY missing from .env', file=sys.stderr)
        sys.exit(1)

    rows = fetch_all()
    segs = build_segments(rows, args.active_days, args.new_days)

    if args.all:
        wanted = list(segs.keys())
    elif args.segment:
        wanted = [s.strip() for s in args.segment.split(',') if s.strip() in segs]
    else:
        print('Nothing to do. Use --all or --segment active,dormant,new,referred,organic')
        sys.exit(0)

    outdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.outdir)
    print(f"Fetched {len(rows)} users. Writing segments to {outdir}:")
    for s in wanted:
        p = os.path.join(outdir, f"users_{s}.csv")
        n = write_csv(p, segs[s])
        print(f"  {s:9s} {n:3d}  -> {p}")

if __name__ == '__main__':
    main()
