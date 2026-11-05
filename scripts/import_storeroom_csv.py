#!/usr/bin/env python3
"""
Convert storeroom CSV export (format A) -> abhihub.documents rows (format B).

What changed vs. the old script
--------------------------------
* Garbage titles/subjects ("3Ee5F02A E187 47A9 Soft ... X6Jlr") are cleaned by using the
  UUID + random suffix hidden in provider_public_id as the key to strip them exactly.
* Subject code, year and exam type (CAE1/CAE2/ESE) are parsed from provider_public_id.
* Subjects are matched by code first, then exact name, then fuzzy name.
* uploader_id = the UUID embedded in the filename (this is what format B does);
  random vaibhavi/wasudha is only a fallback when that profile doesn't exist.
* description is the JSON metadata blob used in format B (not the "Filename Fast-Path" junk).
* file_type: jpg/png/webp/svg -> "image", pdf and Cloudinary raw/.txt -> "pdf".
* program lower-cased ("b.tech"), exam_paper -> papers, sample/placeholder uploads skipped.
* Duplicate check on file_url, provider_public_id and (optionally) sha256 file_hash.
* --dry-run to preview, --compute-hash to fill file_hash by downloading each file.
"""
import os
import re
import csv
import json
import glob
import random
import difflib
import hashlib
import argparse

BASE = os.path.dirname(os.path.abspath(__file__))

UUID_RE = re.compile(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.I)
# UHUL321, UBSL255, UCSLV24, 2BAD01T ...
CODE_RE = re.compile(r'^(?:[a-z]{3,5}\d{2,3}[a-z]?|\d[a-z]{3}\d{2}[a-z])$', re.I)
YEAR_RE = re.compile(r'(?<!\d)(20\d{2})(?!\d)')
EXAM_TOKEN_RE = re.compile(r'(?:^|_)(cae[12]|ese)(?:_|$)', re.I)

EXAM_FROM_TOKEN = {'cae1': 'CAE1', 'cae2': 'CAE2', 'ese': 'ESE'}
# fallback when filename has no cae1/cae2/ese token (edit to match your DB values)
EXAM_FROM_CSV = {
    'cae i': 'CAE1', 'cae 1': 'CAE1', 'cae1': 'CAE1',
    'cae ii': 'CAE2', 'cae 2': 'CAE2', 'cae2': 'CAE2',
    'end sem': 'ESE', 'ese': 'ESE', 'unit test': 'Unit Test',
}
IMAGE_EXT = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'svg'}
CATEGORY_MAP = {'exam_paper': 'papers', 'papers': 'papers'}


# ----------------------------------------------------------------- helpers
def normalize_url(url):
    if not url:
        return ""
    u = url.strip().rstrip('/')
    return 'https://' + u[7:] if u.startswith('http://') else u


def norm_name(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def uuid_from_pid(pid):
    m = UUID_RE.search(pid or '')
    return m.group(1).lower() if m else None


def clean_subject(raw, uid, pid):
    """Strip leading UUID fragments + trailing random suffix, pull out subject code."""
    tokens = (raw or '').split()
    segs = set(uid.split('-')) if uid else set()
    while tokens and tokens[0].lower() in segs:
        tokens.pop(0)

    suffix = (pid or '').rsplit('_', 1)[-1].lower()
    if tokens and tokens[-1].lower() == suffix:
        tokens.pop()

    code = None
    if tokens and CODE_RE.match(tokens[-1]):
        code = tokens.pop().upper()

    return ' '.join(tokens).strip(), code


def parse_year(pid, uid):
    tail = (pid or '')
    if uid:
        tail = tail.split(uid, 1)[-1]
    m = YEAR_RE.search(tail)
    return m.group(1) if m else ''


def parse_exam(pid, csv_exam):
    m = EXAM_TOKEN_RE.search(pid or '')
    if m:
        return EXAM_FROM_TOKEN[m.group(1).lower()]
    key = (csv_exam or '').strip().lower()
    return EXAM_FROM_CSV.get(key) or ((csv_exam or '').strip() or None)


def detect_file_type(url, csv_type):
    ext = url.split('?')[0].rsplit('.', 1)[-1].lower() if '.' in url else ''
    if ext in IMAGE_EXT or (csv_type or '').lower() in IMAGE_EXT:
        return 'image'
    if ext == 'pdf' or '/raw/' in url:
        return 'pdf'
    return ext or (csv_type or '').lower() or 'image'


def sha256_of_url(url):
    import requests
    h = hashlib.sha256()
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        for chunk in r.iter_content(1 << 16):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------- supabase io
def fetch_all(sb, table, cols, page=1000):
    out, start = [], 0
    while True:
        rows = sb.table(table).select(cols).range(start, start + page - 1).execute().data or []
        out.extend(rows)
        if len(rows) < page:
            return out
        start += page


def load_lookups(sb):
    colleges, departments = {}, {}
    for c in fetch_all(sb, 'colleges', 'id, name, abbreviation'):
        for k in (c.get('name'), c.get('abbreviation')):
            if k:
                colleges[k.lower().strip()] = c['id']
    for d in fetch_all(sb, 'departments', 'id, name, abbreviation'):
        for k in (d.get('name'), d.get('abbreviation')):
            if k:
                departments[k.lower().strip()] = d['id']

    by_code, by_name = {}, {}
    for s in fetch_all(sb, 'subjects', 'id, name, subject_code'):
        if s.get('subject_code'):
            by_code[s['subject_code'].strip().upper()] = s['id']
        if s.get('name'):
            by_name[norm_name(s['name'])] = s['id']
    return colleges, departments, by_code, by_name


def match_subject(name, code, by_code, by_name):
    if code and code in by_code:
        return by_code[code], 'code'
    n = norm_name(name)
    if n in by_name:
        return by_name[n], 'name'
    close = difflib.get_close_matches(n, list(by_name), n=1, cutoff=0.85)
    if close:
        return by_name[close[0]], 'fuzzy'
    return None, None


def fallback_uploaders(sb, emails):
    ids = []
    for p in fetch_all(sb, 'profiles', 'id, email'):
        if (p.get('email') or '').strip().lower() in emails:
            ids.append(p['id'])
    return ids


# -------------------------------------------------------------------- main
def run_import(csv_path, dry_run=False, compute_hash=False):
    from dotenv import load_dotenv
    from supabase import create_client, ClientOptions

    load_dotenv(os.path.join(BASE, '..', '.env'))
    url = os.environ.get("SUPABASE_URL")
    key = (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
           or os.environ.get("SUPABASE_PUBLIC_API_KEY"))
    if not url or not key:
        raise SystemExit("[ERROR] Missing SUPABASE_URL or key in .env")

    sb = create_client(url, key.strip("'\""), options=ClientOptions(
        schema="abhihub", persist_session=False, auto_refresh_token=False))

    print("Loading existing documents / lookups / profiles ...")
    existing = fetch_all(sb, 'documents', 'file_url, provider_public_id, file_hash')
    seen_urls = {normalize_url(r['file_url']) for r in existing if r.get('file_url')}
    seen_pids = {r['provider_public_id'] for r in existing if r.get('provider_public_id')}
    seen_hashes = {r['file_hash'] for r in existing if r.get('file_hash')}

    colleges, departments, subj_code, subj_name = load_lookups(sb)
    profile_ids = {p['id'] for p in fetch_all(sb, 'profiles', 'id')}
    fallback = fallback_uploaders(sb, {'vaibhavi@abhihub.com', 'wasudha@abhihub.com'})

    default_college = (colleges.get('ghrce')
                       or colleges.get('g.h. raisoni college of engineering, nagpur')
                       or next(iter(colleges.values()), None))
    default_dept = departments.get('engineering') or next(iter(departments.values()), None)

    to_insert, stats = [], dict(skipped_dup=0, skipped_sample=0, no_url=0,
                                subj_none=0, uploader_fallback=0)

    with open(csv_path, 'r', encoding='utf-8', errors='replace', newline='') as f:
        for row in csv.DictReader(f):
            file_url = (row.get('file_url') or '').strip()
            pid = (row.get('provider_public_id') or '').strip()
            if not file_url:
                stats['no_url'] += 1
                continue
            if pid.startswith('samples/'):
                stats['skipped_sample'] += 1
                continue
            nurl = normalize_url(file_url)
            if nurl in seen_urls or (pid and pid in seen_pids):
                stats['skipped_dup'] += 1
                continue
            seen_urls.add(nurl)
            if pid:
                seen_pids.add(pid)

            uid = uuid_from_pid(pid)
            subject, code = clean_subject(row.get('subject_name') or row.get('title'), uid, pid)
            code = code or ((row.get('subject_code') or '').strip().upper() or None)
            year = parse_year(pid, uid)
            exam = parse_exam(pid, row.get('exam_type'))

            subject_id, how = match_subject(subject, code, subj_code, subj_name)
            if not subject_id:
                stats['subj_none'] += 1

            if uid and uid in profile_ids:
                uploader = uid
            else:
                uploader = random.choice(fallback) if fallback else None
                stats['uploader_fallback'] += 1

            college_id = colleges.get((row.get('college_name') or '').lower().strip()) or default_college
            dept_id = departments.get((row.get('department_name') or '').lower().strip()) or default_dept

            try:
                size = int(row.get('file_size_bytes') or 0)
            except ValueError:
                size = 0

            title = subject or (row.get('title') or 'Untitled Document')
            if exam:
                title = f"{title} - {exam}"

            category = CATEGORY_MAP.get((row.get('document_category') or 'papers').strip(),
                                        (row.get('document_category') or 'papers').strip())

            description = json.dumps({
                "subject": f"{subject} ({code})" if code else subject,
                "year": year,
                "subject_code": code or "",
                "semesters": [],
                "semester": None,
                "text_description": "",
            }, ensure_ascii=False)

            rec = {
                'title': title,
                'college_id': college_id,
                'department_id': dept_id,
                'subject_id': subject_id,
                'uploader_id': uploader,
                'file_url': file_url,
                'storage_provider': (row.get('storage_provider') or 'cloudinary').strip().lower(),
                'provider_public_id': pid or None,
                'file_type': detect_file_type(file_url, row.get('file_type')),
                'file_size_bytes': size,
                'status': (row.get('status') or 'pending').strip().lower(),
                'document_category': category,
                'exam_type': exam,
                'program': (row.get('program') or 'B.Tech').strip().lower(),
                'is_paid': False,
                'price': 0.0,
                'description': description,
            }
            if (row.get('created_at') or '').strip():
                rec['created_at'] = row['created_at'].strip()

            if compute_hash and not dry_run:
                try:
                    h = sha256_of_url(file_url)
                    if h in seen_hashes:
                        stats['skipped_dup'] += 1
                        continue
                    seen_hashes.add(h)
                    rec['file_hash'] = h
                except Exception as e:
                    print(f"  hash failed for {file_url}: {e}")

            to_insert.append(rec)

    print(f"\nNew records: {len(to_insert)} | {stats}")
    if dry_run:
        for r in to_insert[:10]:
            print(f"  {r['title']!r:70} subj={'Y' if r['subject_id'] else 'N'} "
                  f"exam={r['exam_type']} type={r['file_type']}")
        print("Dry run - nothing inserted.")
        return
    if not to_insert:
        return

    inserted = errors = 0
    for i in range(0, len(to_insert), 100):
        chunk = to_insert[i:i + 100]
        try:
            inserted += len(sb.table('documents').insert(chunk).execute().data or [])
        except Exception as e:
            print(f"  chunk {i // 100 + 1} failed ({e}); retrying row-by-row")
            for doc in chunk:
                try:
                    sb.table('documents').insert(doc).execute()
                    inserted += 1
                except Exception as ie:
                    s = str(ie).lower()
                    if 'duplicate' in s or 'unique' in s or '23505' in s:
                        stats['skipped_dup'] += 1
                    else:
                        errors += 1
                        if errors <= 10:
                            print(f"    FAILED {doc['title']!r}: {ie}")

    print(f"\nDone. inserted={inserted} skipped_dup={stats['skipped_dup']} failed={errors}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    default = (glob.glob(os.path.join(BASE, '..', 'data', 'storeroom_documents*.csv')) or [None])[0]
    ap.add_argument('--csv', default=default)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--compute-hash', action='store_true',
                    help='download each file and fill file_hash (sha256)')
    a = ap.parse_args()
    if not a.csv or not os.path.exists(a.csv):
        raise SystemExit(f"[ERROR] CSV not found: {a.csv}")
    run_import(a.csv, a.dry_run, a.compute_hash)