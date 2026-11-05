"""
AbhiHub Search Vocabulary Seed & Backfill Script
Populates search_vocab with subject codes, abbreviations, aliases, colleges, branches, and types.
Seeds abbreviations for top subjects (OOP, ML, UHV, DBMS, OS, DAA, etc.) and college aliases (GHRCE, etc.).
"""
import os
import sys
import re
import logging
from typing import Dict, List, Any, Optional

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from methods.supabase_helper import init_supabase_admin, init_supabase

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

STOP_WORDS = {'for', 'of', 'and', 'the', 'to', 'in', 'with', 'a', 'an', 'on', 'at', 'theory', 'lab', 'practical'}

# Curated subject abbreviation overrides
SUBJECT_ABBR_OVERRIDES: Dict[str, str] = {
    'universal human value': 'UHV',
    'universal human values': 'UHV',
    'universal human value - theory': 'UHV',
    'machine learning': 'ML',
    'machine learning algorithms': 'ML',
    'object oriented programming': 'OOP',
    'database management system': 'DBMS',
    'database management systems': 'DBMS',
    'operating system': 'OS',
    'operating systems': 'OS',
    'computer network': 'CN',
    'computer networks': 'CN',
    'design and analysis of algorithm': 'DAA',
    'design and analysis of algorithms': 'DAA',
    'computer organization and architecture': 'COA',
    'computer organization': 'CO',
    'theory of computation': 'TOC',
    'formal language and automata theory': 'FLAT',
    'web technology': 'WT',
    'web technologies': 'WT',
    'compiler design': 'CD',
    'software engineering': 'SE',
    'artificial intelligence': 'AI',
    'internet of things': 'IOT',
}

# Curated college short names & aliases
COLLEGE_OVERRIDES: Dict[str, Dict[str, Any]] = {
    'g h raisoni': {'short_name': 'GHRCE', 'aliases': ['ghrce', 'g h raisoni', 'raisoni', 'ghrcen']},
    'raisoni': {'short_name': 'GHRCE', 'aliases': ['ghrce', 'g h raisoni', 'raisoni']},
    'institute of technical education': {'short_name': 'ITER', 'aliases': ['iter', 'soa', 'siksha o anusandhan']},
    'kalinga institute': {'short_name': 'KIIT', 'aliases': ['kiit', 'kalinga']},
    'veer surendra': {'short_name': 'VSSUT', 'aliases': ['vssut', 'burla']},
    'odisha university of technology': {'short_name': 'OUTR', 'aliases': ['outr', 'cet', 'college of engineering and technology']},
}

def generate_abbr_from_title(title: str) -> Optional[str]:
    """Generates initials from significant words in title (e.g., Object Oriented Programming -> OOP)."""
    words = [w.strip() for w in re.split(r'[^a-zA-Z0-9]+', title) if w.strip()]
    sig = [w[0].upper() for w in words if w.lower() not in STOP_WORDS]
    if len(sig) >= 2 and len(sig) <= 5:
        return ''.join(sig)
    return None

def normalize_term(term: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^a-zA-Z0-9]+', ' ', str(term or ''))).strip().lower()

def seed_vocab():
    client = init_supabase_admin() or init_supabase()
    if not client:
        logger.error("Supabase client unavailable. Check environment variables.")
        return

    logger.info("1. Fetching colleges, college_departments, and subjects...")
    try:
        colleges_resp = client.table('colleges').select('id, name, abbreviation, popular_name, aliases').execute()
        colleges = colleges_resp.data or []
    except Exception as e:
        logger.error(f"Failed to fetch colleges: {e}")
        colleges = []

    dept_to_colleges: Dict[str, List[str]] = {}
    try:
        cd_resp = client.table('college_departments').select('college_id, department_id').execute()
        for row in (cd_resp.data or []):
            cid = row.get('college_id')
            did = row.get('department_id')
            if cid and did:
                dept_to_colleges.setdefault(str(did), []).append(str(cid))
    except Exception as e:
        logger.warning(f"Could not fetch college_departments: {e}")

    try:
        subjects_resp = client.table('subjects').select('id, name, subject_code, semester, department_id').execute()
        subjects = subjects_resp.data or []
    except Exception as e:
        logger.error(f"Failed to fetch subjects: {e}")
        subjects = []

    logger.info(f"Loaded {len(colleges)} colleges, {len(subjects)} subjects.")

    vocab_entries: List[Dict[str, Any]] = []
    seen_keys = set()
    NIL_UUID = '00000000-0000-0000-0000-000000000000'

    def add_entry(kind: str, term: str, label: str, ref_id: Optional[str] = None, college_id: Optional[str] = None, weight: int = 0):
        norm = normalize_term(term)
        if not norm or len(norm) < 2:
            return
        effective_ref_id = ref_id or NIL_UUID
        key = (kind, norm, effective_ref_id)
        if key in seen_keys:
            return
        seen_keys.add(key)
        vocab_entries.append({
            'kind': kind,
            'term': norm,
            'label': label,
            'ref_id': effective_ref_id,
            'college_id': college_id,
            'weight': weight
        })

    # 1. Colleges
    logger.info("2. Processing colleges...")
    for col in colleges:
        c_id = col.get('id')
        name = col.get('name', '').strip()
        n_low = name.lower()

        short_name = None
        aliases = []
        for pat, info in COLLEGE_OVERRIDES.items():
            if pat in n_low:
                short_name = info['short_name']
                aliases = info['aliases']
                break

        if not short_name:
            short_name = generate_abbr_from_title(name)

        # Update college record if short_name or aliases found
        if short_name or aliases:
            try:
                update_payload = {}
                if short_name:
                    update_payload['short_name'] = short_name
                if aliases:
                    update_payload['aliases'] = aliases
                client.table('colleges').update(update_payload).eq('id', c_id).execute()
            except Exception as upd_err:
                logger.warning(f"Could not update college {name}: {upd_err}")

        # Add vocab entries
        if short_name:
            add_entry('college', short_name, f"{short_name} ({name})", ref_id=c_id, college_id=c_id, weight=100)
        for al in aliases:
            add_entry('alias', al, f"{short_name or name}", ref_id=c_id, college_id=c_id, weight=90)
        add_entry('college', name, name, ref_id=c_id, college_id=c_id, weight=80)

    # 2. Subjects
    logger.info("3. Processing subjects...")
    for subj in subjects:
        s_id = subj.get('id')
        name = subj.get('name', '').strip()
        code = subj.get('subject_code', '').strip()
        dept_id = str(subj.get('department_id') or '')
        c_ids = dept_to_colleges.get(dept_id, [None])
        n_low = name.lower()

        abbr = None
        for pat, ab in SUBJECT_ABBR_OVERRIDES.items():
            if pat in n_low:
                abbr = ab
                break
        if not abbr:
            abbr = generate_abbr_from_title(name)

        if abbr:
            try:
                client.table('subjects').update({'abbreviation': abbr}).eq('id', s_id).execute()
            except Exception:
                pass

        # Vocab entries (register for each affiliated college if any)
        display_label = f"{code} - {name}" if code else name
        for c_id in c_ids:
            if code:
                add_entry('subject_code', code, display_label, ref_id=s_id, college_id=c_id, weight=100)
                clean_code = re.sub(r'[^a-zA-Z0-9]', '', code)
                if clean_code != code:
                    add_entry('subject_code', clean_code, display_label, ref_id=s_id, college_id=c_id, weight=95)

            if abbr:
                add_entry('abbreviation', abbr, f"{abbr} = {name}", ref_id=s_id, college_id=c_id, weight=90)
                add_entry('alias', abbr, f"{abbr} = {name}", ref_id=s_id, college_id=c_id, weight=90)

            add_entry('subject_name', name, display_label, ref_id=s_id, college_id=c_id, weight=80)

    # 3. Standard Types
    logger.info("4. Adding standard document types & shortcuts...")
    type_mappings = [
        ('Notes', ['notes', 'note', 'handwritten notes', 'lecture notes']),
        ('Paper', ['paper', 'papers', 'pyq', 'pyqs', 'previous year question paper', 'question paper', 'exam paper']),
        ('Question Bank', ['question bank', 'qb', 'q bank', 'imp questions']),
        ('Practical', ['practical', 'lab', 'lab manual', 'experiment', 'viva']),
        ('Syllabus', ['syllabus', 'curriculum']),
    ]
    for label, terms in type_mappings:
        for t in terms:
            add_entry('type', t, label, weight=70)

    # 4. Standard Branches
    logger.info("5. Adding branch aliases...")
    branch_mappings = [
        ('CSE', ['cse', 'computer science and engineering', 'computer science']),
        ('IT', ['it', 'information technology']),
        ('AI & DS', ['aids', 'ai ds', 'artificial intelligence and data science']),
        ('AI & ML', ['aiml', 'ai ml', 'artificial intelligence and machine learning']),
        ('ECE', ['ece', 'etc', 'electronics and communication']),
        ('EE', ['ee', 'eee', 'electrical engineering']),
        ('ME', ['me', 'mechanical engineering']),
        ('CE', ['ce', 'civil engineering']),
    ]
    for b_label, terms in branch_mappings:
        for t in terms:
            add_entry('branch', t, b_label, weight=65)

    # 5. Flush to search_vocab table in chunks
    logger.info(f"6. Upserting {len(vocab_entries)} entries into search_vocab...")
    try:
        client.table('search_vocab').delete().neq('weight', -9999).execute()
    except Exception as clear_err:
        logger.warning(f"Note on initial clear: {clear_err}")

    chunk_size = 100
    inserted = 0
    for i in range(0, len(vocab_entries), chunk_size):
        chunk = vocab_entries[i:i + chunk_size]
        try:
            client.table('search_vocab').upsert(chunk, on_conflict='kind,term,ref_id').execute()
            inserted += len(chunk)
        except Exception as upsert_err:
            # Fallback to simple insert
            try:
                client.table('search_vocab').insert(chunk).execute()
                inserted += len(chunk)
            except Exception as ins_err:
                logger.warning(f"Chunk {i}-{i+chunk_size} skipped: {ins_err}")

    logger.info(f"Completed! Seeded {inserted} search vocabulary records.")

if __name__ == '__main__':
    seed_vocab()
