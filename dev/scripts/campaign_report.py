#!/usr/bin/env python3
"""
campaign_report.py — Measure a sent email campaign's conversion.

Reads exports/send_log.csv (written by exam_pack_drip.py), then for each
recipient queries the live DB (abhihub.profiles) to see whether they:
  - returned (last_active_at after the send date)  -> re-engagement
  - invited someone (referral_count > 0)            -> referral conversion

Outputs a summary to stdout and writes exports/campaign_report.csv.

Usage:
  python dev/scripts/campaign_report.py
  python dev/scripts/campaign_report.py --segment dormant
"""
import argparse
import csv
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Load .env (same helper shape as exam_pack_drip)
def _load_env():
    p = os.path.join(ROOT, '.env')
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'").strip()

_load_env()

SEND_LOG = os.path.join(ROOT, 'exports', 'send_log.csv')
REPORT = os.path.join(ROOT, 'exports', 'campaign_report.csv')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--segment', default='', help='filter send_log by segment')
    args = ap.parse_args()

    if not os.path.exists(SEND_LOG):
        print(f'No send log at {SEND_LOG}. Run exam_pack_drip.py --send first.', file=sys.stderr)
        sys.exit(1)

    rows = list(csv.DictReader(open(SEND_LOG, encoding='utf-8')))
    if args.segment:
        rows = [r for r in rows if r.get('segment') == args.segment]
    if not rows:
        print('No sends to report.')
        return

    # unique recipients
    recips = {}
    for r in rows:
        recips.setdefault(r['to'], r)
    print(f"Campaign sends: {len(rows)}  | unique recipients: {len(recips)}")

    try:
        from methods.supabase_helper import init_supabase
        client = init_supabase()
    except Exception as e:
        print(f"Supabase unavailable: {e}")
        client = None

    returned = 0
    invited = 0
    detail = []
    for to, r in recips.items():
        sent_at = r.get('sent_at', '')
        try:
            sent_dt = datetime.fromisoformat(sent_at) if sent_at else None
        except Exception:
            sent_dt = None
        rec = {'email': to, 'code': r.get('code', ''), 'sent_at': sent_at,
               'returned': 'unknown', 'invited': 'unknown'}
        if client:
            res = client.table('profiles').select('last_active_at, referral_count, referred_by').eq('email', to).limit(1).execute()
            data = (res.data or [{}])[0]
            la = data.get('last_active_at')
            cnt = data.get('referral_count', 0) or 0
            # returned if last activity is after the send (or within the campaign window)
            if la and sent_dt:
                try:
                    la_dt = datetime.fromisoformat(la.replace('Z', '+00:00'))
                    if la_dt >= sent_dt:
                        returned += 1
                        rec['returned'] = 'yes'
                    else:
                        rec['returned'] = 'no'
                except Exception:
                    rec['returned'] = 'unknown'
            elif la:
                rec['returned'] = 'active'  # active but timestamp unparseable
            if cnt and cnt > 0:
                invited += 1
                rec['invited'] = 'yes'
            else:
                rec['invited'] = 'no'
        detail.append(rec)

    total = len(recips)
    print(f"\nRe-engaged (returned after send): {returned}/{total}  ({100*returned//total if total else 0}%)")
    print(f"Invited someone (referral_count>0): {invited}/{total}  ({100*invited//total if total else 0}%)")

    with open(REPORT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['email', 'code', 'sent_at', 'returned', 'invited'])
        w.writeheader()
        w.writerows(detail)
    print(f"\nDetail -> {REPORT}")


if __name__ == '__main__':
    main()
