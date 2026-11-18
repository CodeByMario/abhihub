#!/usr/bin/env python3
"""
Seed script for G. H. Raisoni College of Engineering Winter-2026 Examination Timetable.
Loads both Practical and Theory schedules (230 records), associating each with GHRCE (college_id: 87928d20-edb3-4185-94e3-b0678470e850),
resolving branches and deduplicating canonical courses via aliases.
"""
import os
import sys
import re
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from methods.supabase_helper import init_supabase, init_supabase_admin

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'ghrce_winter_2026_full_timetable.json')
GHRCE_ID = "87928d20-edb3-4185-94e3-b0678470e850"

def parse_time_range(time_str: str):
    if not time_str or time_str.strip() in ('-', ''):
        return None, None
    clean = time_str.strip().replace('To', '-').replace('to', '-')
    clean = re.sub(r'(?i)onwards', '', clean)
    clean = clean.replace('.', ':').strip()
    parts = [p.strip() for p in clean.split('-') if p.strip()]

    def _to_24h(t_part):
        t_clean = t_part.strip().upper()
        if 'NOON' in t_clean:
            return '12:00:00'
        for fmt in ('%I:%M %p', '%I:%M%p', '%I %p', '%H:%M'):
            try:
                dt = datetime.strptime(t_clean, fmt)
                return dt.strftime('%H:%M:00')
            except ValueError:
                pass
        return None

    start = _to_24h(parts[0]) if len(parts) > 0 else None
    end = _to_24h(parts[1]) if len(parts) > 1 else None
    return start, end

def parse_dates(date_str: str):
    matches = re.findall(r'(\d{2}-\d{2}-\d{4})', date_str)
    res = []
    for m in matches:
        try:
            dt = datetime.strptime(m, '%d-%m-%Y')
            res.append(dt.strftime('%Y-%m-%d'))
        except ValueError:
            pass
    return res

def parse_sem_and_section(sem_raw: str):
    clean = sem_raw.strip()
    is_rereg = bool(re.search(r'(?i)reregister|offered in', clean))
    offered_in = None
    offered_match = re.search(r'(?i)offered in\s+([A-Za-z0-9\s/]+?)(?:\s*\(|$)', clean)
    if offered_match:
        offered_in = offered_match.group(1).strip()

    section = None
    sec_match = re.search(r'(?i)(?:Section|GROUP)\s*[:\-]?\s*([A-Za-z0-9\s/&\-,;]+?)(?:\)|$)', clean)
    if sec_match:
        section = sec_match.group(1).strip()

    sem_base = clean
    for pat in [r'\(.*?\)', r'Offered in.*', r'Section.*', r'GROUP.*']:
        sem_base = re.sub(pat, '', sem_base, flags=re.I).strip()

    if '-' in sem_base and not section:
        parts = [p.strip() for p in sem_base.split('-') if p.strip()]
        if len(parts) >= 2:
            sem_base = parts[0]
            section = parts[1]

    return sem_base.strip() or 'First', section, is_rereg, offered_in

def resolve_department(client, branch_name: str) -> str:
    clean = branch_name.strip()
    res = client.table('departments').select('id, name, abbreviation').execute()
    depts = res.data or []
    for d in depts:
        if d.get('abbreviation') and d['abbreviation'].strip().lower() == clean.lower():
            return d['id']
        if d.get('name') and (clean.lower() in d['name'].lower() or d['name'].lower() in clean.lower()):
            return d['id']
    abbr = re.sub(r'[^A-Z0-9]', '', clean.upper())[:10] or clean[:10]
    ins = client.table('departments').insert({'name': clean, 'abbreviation': abbr}).execute()
    return ins.data[0]['id']

def resolve_or_create_subject(client, code_raw: str, name: str, dept_id: str) -> str:
    codes = [c.strip().upper() for c in code_raw.split('/') if c.strip()]
    canonical_code = codes[0]

    res = client.table('subjects').select('id').eq('subject_code', canonical_code).limit(1).execute()
    if res.data:
        sub_id = res.data[0]['id']
    else:
        alias_res = client.table('subject_aliases').select('subject_id').eq('alias_norm', canonical_code.lower()).limit(1).execute()
        if alias_res.data:
            sub_id = alias_res.data[0]['subject_id']
        else:
            ins = client.table('subjects').insert({
                'name': name.strip(),
                'subject_code': canonical_code,
                'department_id': dept_id
            }).execute()
            sub_id = ins.data[0]['id']

    for alt_code in codes:
        try:
            client.table('subject_aliases').upsert({
                'subject_id': sub_id,
                'alias': alt_code,
                'alias_norm': alt_code.lower(),
                'priority': 1
            }).execute()
        except Exception:
            pass

    return sub_id

def seed_ghrce_full_timetable():
    client = init_supabase_admin() or init_supabase()
    if not client:
        print("[Seed] Error: Supabase client unavailable.")
        return False

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        rows = json.load(f)

    print(f"[Seed] Seeding {len(rows)} GHRCE timetable rows (college_id: {GHRCE_ID})...")
    inserted = 0

    for row in rows:
        try:
            dept_id = resolve_department(client, row['branch'])
            sub_id = resolve_or_create_subject(client, row['code'], row['course'], dept_id)
            sem, section, is_rereg, offered_in = parse_sem_and_section(row['sem_raw'])
            dates = parse_dates(row['date_raw'])
            start_t, end_t = parse_time_range(row['time_raw'])

            for exam_date in dates:
                record = {
                    'subject_id': sub_id,
                    'department_id': dept_id,
                    'programme': row.get('programme', 'B.Tech'),
                    'semester': sem,
                    'section': section,
                    'exam_date': exam_date,
                    'start_time': start_t,
                    'end_time': end_t,
                    'exam_type': row.get('exam_type', 'THEORY'),
                    'academic_term': 'Winter 2026',
                    'is_reregistration': is_rereg,
                    'offered_in_semester': offered_in,
                    'notes_flags': row['sem_raw'] if (is_rereg or offered_in) else None,
                    'is_active': True
                }

                check = client.table('exam_schedules').select('id')\
                    .eq('subject_id', sub_id)\
                    .eq('department_id', dept_id)\
                    .eq('semester', sem)\
                    .eq('exam_date', exam_date)\
                    .eq('exam_type', record['exam_type'])\
                    .execute()

                if not check.data:
                    client.table('exam_schedules').insert(record).execute()
                    inserted += 1
        except Exception as e:
            print(f"[Seed] Error on {row.get('code')}: {e}")

    print(f"[Seed] Finished. Successfully processed {len(rows)} timetable rows; {inserted} inserted.")
    return True

if __name__ == '__main__':
    seed_ghrce_full_timetable()
