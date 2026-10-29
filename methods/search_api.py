"""
Search API V3 Module
High-efficiency, in-memory taxonomy resolution, tiered ranking,
autocomplete (/api/v2/suggest), and graceful search relaxation.
"""
import re
import json
import time
import math
import logging
import threading
from typing import Dict, List, Optional, Tuple, Any
from flask import request, jsonify
from methods.supabase_helper import init_supabase, init_supabase_admin, _cache_get, _cache_set

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 1. Normalization Primitives
# -----------------------------------------------------------------------------
_NON_ALNUM = re.compile(r'[^a-zA-Z0-9]+')
_MULTI_SPACE = re.compile(r'\s+')

def norm_code(text: Optional[str]) -> str:
    """Normalize subject code: 'CSE-2001' -> 'cse2001'"""
    if not text:
        return ''
    return _NON_ALNUM.sub('', text).lower()

def norm_text(text: Optional[str]) -> str:
    """Normalize general text: lowercase, remove non-alnum, single spaced."""
    if not text:
        return ''
    cleaned = _NON_ALNUM.sub(' ', text).lower()
    return _MULTI_SPACE.sub(' ', cleaned).strip()

# -----------------------------------------------------------------------------
# 2. Built-in Curated Fallback Dictionaries (Zero-DB bootstrap & seed parity)
# -----------------------------------------------------------------------------
DEFAULT_COLLEGE_ALIASES = {
    'iter': {'name_pattern': r'iter|institute of technical education|siksha.*anusandhan|soa', 'is_group': False},
    'soa': {'name_pattern': r'iter|institute of technical education|soa|siksha.*anusandhan', 'is_group': True},
    'kiit': {'name_pattern': r'kiit|kalinga institute', 'is_group': False},
    'vssut': {'name_pattern': r'vssut|veer surendra', 'is_group': False},
    'outr': {'name_pattern': r'outr|odisha university of technology', 'is_group': False},
    'cet': {'name_pattern': r'college of engineering|cet|odisha university of technology', 'is_group': False},
}

DEFAULT_DEPARTMENT_ALIASES: Dict[str, List[str]] = {
    'cse': ['computer science and engineering', 'computer science', 'computer technology'],
    'cs': ['computer science and engineering', 'computer science'],
    'it': ['information technology'],
    'ai': ['artificial intelligence', 'artificial intelligence and data science', 'artificial intelligence and machine learning'],
    'aiml': ['artificial intelligence and machine learning', 'ai & ml'],
    'aids': ['artificial intelligence and data science', 'ai & ds'],
    'ds': ['data science'],
    'ece': ['electronics and communication engineering', 'electronics and telecommunication engineering', 'electronics engineering', 'etc'],
    'etc': ['electronics and telecommunication engineering', 'electronics and communication engineering'],
    'ee': ['electrical engineering'],
    'eee': ['electrical and electronics engineering'],
    'mech': ['mechanical engineering'],
    'mechanical': ['mechanical engineering'],
    'civil': ['civil engineering'],
    'ce': ['civil engineering'],
    'chem': ['chemical engineering'],
    'aero': ['aerospace engineering', 'aeronautical engineering'],
    'biotech': ['biotechnology']
}

DEFAULT_SUBJECT_ALIASES = {
    'os': ['operating system', 'operating systems'],
    'dbms': ['database management', 'database management systems'],
    'db': ['database management'],
    'daa': ['design and analysis of algorithms', 'analysis of algorithms', 'algorithms'],
    'algo': ['design and analysis of algorithms', 'algorithms'],
    'algorithms': ['design and analysis of algorithms', 'algorithms'],
    'toc': ['theory of computation', 'formal languages', 'automata'],
    'flat': ['formal languages and automata theory', 'theory of computation'],
    'automata': ['theory of computation', 'formal languages and automata theory'],
    'coa': ['computer organization', 'computer architecture', 'computer organization and architecture'],
    'cao': ['computer architecture and organization', 'computer organization'],
    'cn': ['computer networks', 'computer network'],
    'networks': ['computer networks'],
    'wt': ['web technology', 'web technologies', 'internet and web technology'],
    'webtech': ['web technology', 'web technologies'],
    'oop': ['object oriented programming', 'object oriented programming using java'],
    'oops': ['object oriented programming'],
    'java': ['object oriented programming using java', 'java programming'],
    'dld': ['digital logic design', 'digital electronics'],
    'de': ['digital electronics', 'digital logic design'],
    'ai': ['artificial intelligence'],
    'ml': ['machine learning'],
    'cd': ['compiler design'],
    'se': ['software engineering'],
    'ds': ['data structures', 'data structures and algorithms'],
    'dsa': ['data structures and algorithms', 'data structures'],
    'mp': ['microprocessor', 'microprocessors'],
    'up': ['microprocessor', 'microprocessors'],
    'mc': ['microcontroller', 'microcontrollers'],
    'm1': ['mathematics i', 'mathematics 1', 'engineering mathematics i'],
    'm2': ['mathematics ii', 'mathematics 2', 'engineering mathematics ii'],
    'm3': ['mathematics iii', 'mathematics 3', 'engineering mathematics iii', 'transform calculus'],
    'maths': ['mathematics'],
    'maths 1': ['mathematics i', 'mathematics 1'],
    'maths 2': ['mathematics ii', 'mathematics 2'],
    'maths 3': ['mathematics iii', 'mathematics 3'],
    'chem': ['chemistry', 'engineering chemistry', 'environmental chemistry'],
    'physics': ['physics', 'engineering physics', 'applied physics'],
    'stats': ['statistics', 'probability and statistics', 'linear algebra and statistics'],
    'calc': ['calculus', 'matrices and differential calculus', 'integral calculus and differential equations'],
    'calculus': ['matrices and differential calculus', 'integral calculus and differential equations'],
    'math': ['mathematics', 'calculus', 'linear algebra'],
    'python': ['python', 'computer programming', 'data structures'],
    'c': ['computer programming'],
    'data analytics': ['foundation of data analytics', 'data analytics'],
    'drones': ['introduction to drones'],
    'devices': ['introduction to discrete devices and circuits'],
}

EXAM_EQUIVALENCES: Dict[str, List[str]] = {
    'midsem': ['midsem', 'mid sem', 'midterm', 'mid term', 'cae1', 'cae 1', 'cae2', 'cae 2', 'mst1', 'mst2', 'cia1', 'cia2', 'internal', 'test 1', 'test 2'],
    'mid sem': ['midsem', 'mid sem', 'midterm', 'mid term', 'cae1', 'cae 1', 'cae2', 'cae 2', 'mst1', 'mst2'],
    'midsem 1': ['midsem 1', 'midsem-1', 'mid sem 1', 'cae1', 'cae 1', 'cae-1', 'mst1', 'test 1', 'internal 1'],
    'midsem 2': ['midsem 2', 'midsem-2', 'mid sem 2', 'cae2', 'cae 2', 'cae-2', 'mst2', 'test 2', 'internal 2'],
    'cae1': ['cae1', 'cae 1', 'cae-1', 'midsem 1', 'mid sem 1', 'midsem', 'mst1', 'test 1'],
    'cae2': ['cae2', 'cae 2', 'cae-2', 'midsem 2', 'mid sem 2', 'midsem', 'mst2', 'test 2'],
    'cae 1': ['cae1', 'cae 1', 'cae-1', 'midsem 1', 'mid sem 1', 'midsem', 'mst1', 'test 1'],
    'cae 2': ['cae2', 'cae 2', 'cae-2', 'midsem 2', 'mid sem 2', 'midsem', 'mst2', 'test 2'],
    'endsem': ['endsem', 'end sem', 'endterm', 'end term', 'ese', 'final', 'external'],
    'end sem': ['endsem', 'end sem', 'endterm', 'end term', 'ese', 'final', 'external'],
    'ese': ['ese', 'endsem', 'end sem', 'endterm', 'end term', 'final', 'external'],
}

COMMON_SUBJECT_SEMESTERS: Dict[str, int] = {
    'operating system': 4,
    'database management system': 4,
    'data structures': 3,
    'design and analysis of algorithm': 4,
    'computer organization': 3,
    'formal language': 5,
    'theory of computation': 5,
    'compiler design': 6,
    'computer network': 5,
    'web technology': 5,
    'matrices and differential calculus': 1,
    'integral calculus': 2,
    'linear algebra': 3,
    'engineering physics': 1,
    'applied physics': 2,
    'computer programming': 1,
    'discrete mathematics': 3,
}

def get_subj_semester(s: Optional[Dict[str, Any]]) -> Optional[int]:
    """Retrieve semester from subject row, or deduce from common engineering curriculums."""
    if not s:
        return None
    if s.get('semester') and str(s.get('semester')).isdigit():
        return int(s.get('semester'))
    s_name = norm_text(s.get('name'))
    for k, sem in COMMON_SUBJECT_SEMESTERS.items():
        if k in s_name:
            return sem
    return None

# -----------------------------------------------------------------------------
# 3. In-Memory Taxonomy Store & Auto-Refresh
# -----------------------------------------------------------------------------
_TAXONOMY_LOCK = threading.Lock()
_TAXONOMY_CACHE: Dict[str, Any] = {
    'colleges': [],
    'departments': [],
    'subjects': [],
    'subject_aliases': [],
    'college_aliases': [],
    'last_updated': 0
}
_TAXONOMY_TTL = 300  # 5 minutes

def get_taxonomy() -> Dict[str, Any]:
    """Retrieve in-memory academic taxonomy, reloading if expired."""
    global _TAXONOMY_CACHE
    now = time.time()
    if _TAXONOMY_CACHE['last_updated'] > 0 and (now - _TAXONOMY_CACHE['last_updated']) < _TAXONOMY_TTL:
        return _TAXONOMY_CACHE

    with _TAXONOMY_LOCK:
        if _TAXONOMY_CACHE['last_updated'] > 0 and (now - _TAXONOMY_CACHE['last_updated']) < _TAXONOMY_TTL:
            return _TAXONOMY_CACHE

        client = init_supabase_admin() or init_supabase()
        if not client:
            return _TAXONOMY_CACHE

        try:
            # 1. Colleges
            col_res = client.table('colleges').select('id, name, abbreviation').execute()
            colleges = col_res.data or []
            abbr_to_colleges: Dict[str, List[Dict[str, Any]]] = {}
            for c in colleges:
                c['name_norm'] = norm_text(c.get('name'))
                c_abbr = norm_text(c.get('abbreviation'))
                c['abbr_norm'] = c_abbr
                if c_abbr:
                    abbr_to_colleges.setdefault(c_abbr, []).append(c)

            # 2. Departments
            dept_res = client.table('departments').select('id, name, abbreviation').execute()
            departments = dept_res.data or []
            for d in departments:
                d['name_norm'] = norm_text(d.get('name'))
                d['abbr_norm'] = norm_text(d.get('abbreviation'))

            # 3. Subjects
            subj_res = client.table('subjects').select('id, department_id, name, subject_code, semester').execute()
            subjects = subj_res.data or []
            for s in subjects:
                s['name_norm'] = norm_text(s.get('name'))
                s['code_norm'] = norm_code(s.get('subject_code'))

            # 4. Subject Aliases: DB rows + Curated built-in aliases
            subject_aliases = []
            seen_aliases = set()
            try:
                alias_res = client.table('subject_aliases').select('subject_id, alias, priority').execute()
                for a in (alias_res.data or []):
                    an = norm_text(a.get('alias'))
                    subject_aliases.append({
                        'subject_id': a['subject_id'],
                        'alias': a.get('alias'),
                        'alias_norm': an,
                        'priority': a.get('priority', 1)
                    })
                    seen_aliases.add((an, a['subject_id']))
            except Exception as ae:
                logger.debug(f"[Search Taxonomy] DB aliases query note: {ae}")

            # Merge curated built-in dictionary
            for alias_k, patterns in DEFAULT_SUBJECT_ALIASES.items():
                an = norm_text(alias_k)
                for s in subjects:
                    s_name_norm = s.get('name_norm', '')
                    for pat in patterns:
                        if pat in s_name_norm or re.search(r'\b' + re.escape(pat) + r'\b', s_name_norm):
                            if (an, s['id']) not in seen_aliases:
                                subject_aliases.append({
                                    'subject_id': s['id'],
                                    'alias': alias_k,
                                    'alias_norm': an,
                                    'priority': 1
                                })
                                seen_aliases.add((an, s['id']))
                            break

            # 5. College Aliases: DB rows + Curated built-in college aliases
            college_aliases = []
            seen_ca = set()
            try:
                ca_res = client.table('college_aliases').select('college_id, alias, is_group').execute()
                for ca in (ca_res.data or []):
                    can = norm_text(ca.get('alias'))
                    college_aliases.append({
                        'college_id': ca['college_id'],
                        'alias': ca.get('alias'),
                        'alias_norm': can,
                        'is_group': ca.get('is_group', False)
                    })
                    seen_ca.add((can, ca['college_id']))
            except Exception as ce:
                logger.debug(f"[Search Taxonomy] DB college_aliases note: {ce}")

            for alias_k, meta in DEFAULT_COLLEGE_ALIASES.items():
                can = norm_text(alias_k)
                pat = meta['name_pattern']
                is_grp = meta['is_group']
                for c in colleges:
                    c_name = norm_text(c.get('name'))
                    c_abbr = norm_text(c.get('abbreviation'))
                    if re.search(pat, c_name) or re.search(pat, c_abbr):
                        if (can, c['id']) not in seen_ca:
                            college_aliases.append({
                                'college_id': c['id'],
                                'alias': alias_k,
                                'alias_norm': can,
                                'is_group': is_grp
                            })
                            seen_ca.add((can, c['id']))

            # 6. Search Vocabulary (instant suggestion & typo lookup)
            search_vocab = []
            try:
                vocab_res = client.table('search_vocab').select('kind, term, label, ref_id, college_id, weight').execute()
                search_vocab = vocab_res.data or []
            except Exception as ve:
                logger.debug(f"[Search Taxonomy] Vocab query note: {ve}")

            _TAXONOMY_CACHE = {
                'colleges': colleges,
                'abbr_to_colleges': abbr_to_colleges,
                'departments': departments,
                'subjects': subjects,
                'subject_aliases': subject_aliases,
                'college_aliases': college_aliases,
                'vocab': search_vocab,
                'last_updated': time.time()
            }
        except Exception as e:
            logger.error(f"[Search Taxonomy] Error reloading taxonomy: {e}")

    return _TAXONOMY_CACHE

# -----------------------------------------------------------------------------
# 3.1 In-Memory Document Store (< 2ms instantaneous search)
# -----------------------------------------------------------------------------
_DOCUMENTS_LOCK = threading.Lock()
_DOCUMENTS_CACHE: Dict[str, Any] = {
    'documents': [],
    'last_updated': 0
}
_DOCUMENTS_TTL = 120  # 2 minutes TTL

def invalidate_search_cache():
    """Force refresh of search documents cache."""
    global _DOCUMENTS_CACHE
    with _DOCUMENTS_LOCK:
        _DOCUMENTS_CACHE['last_updated'] = 0

def get_cached_documents(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Retrieve preloaded approved documents catalogue in memory for instantaneous search."""
    global _DOCUMENTS_CACHE
    now = time.time()
    if not force_refresh and _DOCUMENTS_CACHE['last_updated'] > 0 and (now - _DOCUMENTS_CACHE['last_updated']) < _DOCUMENTS_TTL:
        return _DOCUMENTS_CACHE['documents']

    with _DOCUMENTS_LOCK:
        if not force_refresh and _DOCUMENTS_CACHE['last_updated'] > 0 and (now - _DOCUMENTS_CACHE['last_updated']) < _DOCUMENTS_TTL:
            return _DOCUMENTS_CACHE['documents']

        client = init_supabase_admin() or init_supabase()
        if not client:
            return _DOCUMENTS_CACHE['documents']

        try:
            res = client.table('documents').select(
                'id, title, file_url, document_category, file_type, '
                'view_count, like_count, bookmark_count, created_at, description, '
                'college_id, department_id, subject_id, search_text, '
                'profiles!documents_uploader_id_fkey(full_name), '
                'subjects(id, name, subject_code, semester), colleges(id, name)'
            ).in_('status', ['approved', 'pending']).order('created_at', desc=True).limit(5000).execute()

            docs = res.data or []
            for d in docs:
                d['title_norm'] = norm_text(d.get('title'))
                st = d.get('search_text') or ''
                d['search_text_norm'] = norm_text(st) if st else ''
            _DOCUMENTS_CACHE['documents'] = docs
            _DOCUMENTS_CACHE['last_updated'] = now
            return docs
        except Exception as e:
            logger.warning(f"[Search API] Documents cache error: {e}")
            return _DOCUMENTS_CACHE['documents']

# -----------------------------------------------------------------------------
# 4. In-Memory Query Parser (< 1ms)
# -----------------------------------------------------------------------------
_SEM_REGEX = re.compile(r'\b(?:sem(?:ester)?|s)\s*([1-8])\b|\b([1-8])(?:st|nd|rd|th)\s*sem(?:ester)?\b', re.IGNORECASE)
_YEAR_REGEX = re.compile(r'\b(201[5-9]|202[0-9])\b')
_CATEGORY_REGEX = re.compile(r'\b(pyqs?|previous year|question papers?|notes?|practicals?|lab manuals?|syllabus)\b', re.IGNORECASE)
_AUTHOR_REGEX = re.compile(r'\b(?:by|author|prof|dr|uploaded\s+by)[:\s]+([a-zA-Z0-9_\.]{2,30}(?:\s+[a-zA-Z0-9_\.]{2,30})?)\b', re.IGNORECASE)

def parse_search_intent(query: str, client_college_id: str = None) -> Dict[str, Any]:
    """Parse user query in memory to resolve entities, filters, and subject keywords."""
    taxonomy = get_taxonomy()
    parsed: Dict[str, Any] = {
        'original_query': query,
        'college_ids': [],
        'college_id': None,
        'college_name': None,
        'college_abbr': None,
        'department_id': None,
        'department_name': None,
        'department_abbr': None,
        'author': None,
        'semester': None,
        'category': None,
        'year': None,
        'remaining_tokens': [],
        'matched_subjects': [],
        'match_reason': None
    }

    if client_college_id and client_college_id.upper() != 'ALL' and len(client_college_id) == 36:
        parsed['college_ids'].append(client_college_id)
        parsed['college_id'] = client_college_id

    raw = query.strip()
    if not raw:
        return parsed

    # 1. Extract Semester
    sem_match = _SEM_REGEX.search(raw)
    if sem_match:
        sem_val = sem_match.group(1) or sem_match.group(2)
        parsed['semester'] = int(sem_val)
        raw = _SEM_REGEX.sub(' ', raw)

    # 2. Extract Year
    yr_match = _YEAR_REGEX.search(raw)
    if yr_match:
        parsed['year'] = yr_match.group(1)
        raw = _YEAR_REGEX.sub(' ', raw)

    # 3. Extract Document Category
    cat_match = _CATEGORY_REGEX.search(raw)
    if cat_match:
        found_cat = cat_match.group(1).lower()
        if 'pyq' in found_cat or 'question' in found_cat or 'year' in found_cat:
            parsed['category'] = 'Papers'
        elif 'note' in found_cat:
            parsed['category'] = 'Notes'
        elif 'practical' in found_cat or 'lab' in found_cat:
            parsed['category'] = 'Practicals'
        elif 'syllabus' in found_cat:
            parsed['category'] = 'Syllabus'
        raw = _CATEGORY_REGEX.sub(' ', raw)

    # 4. Extract Exam Term
    exam_term = None
    _EXAM_REGEX = re.compile(r'\b(midsem\s*[12]?|mid\s*sem\s*[12]?|midterm\s*[12]?|endsem|end\s*sem|endterm|cae\s*[12]|ese|quiz|test\s*[1-9]|unit\s*[1-9])\b', re.IGNORECASE)
    exam_match = _EXAM_REGEX.search(raw)
    if exam_match:
        exam_term = norm_text(exam_match.group(1))
        raw = _EXAM_REGEX.sub(' ', raw)

    # 5. Extract Department / Branch
    norm_dept_raw = f" {norm_text(raw)} "
    found_dept = None
    matched_dept_alias = None

    for dept_alias, dept_patterns in DEFAULT_DEPARTMENT_ALIASES.items():
        if f" {dept_alias} " in norm_dept_raw:
            matched_dept_alias = dept_alias
            for d in taxonomy.get('departments', []):
                d_abbr = d.get('abbr_norm') or ''
                d_name = d.get('name_norm') or ''
                if d_abbr == dept_alias or any(p in d_name for p in dept_patterns):
                    found_dept = d
                    break
            raw = re.sub(r'\b' + re.escape(dept_alias) + r'\b', ' ', raw, flags=re.IGNORECASE)
            break

    if not found_dept:
        for d in taxonomy.get('departments', []):
            d_abbr = d.get('abbr_norm')
            if d_abbr and len(d_abbr) >= 2 and f" {d_abbr} " in norm_dept_raw:
                found_dept = d
                raw = re.sub(r'\b' + re.escape(d_abbr) + r'\b', ' ', raw, flags=re.IGNORECASE)
                break

    if found_dept:
        parsed['department_id'] = found_dept.get('id')
        parsed['department_name'] = found_dept.get('name')
        parsed['department_abbr'] = found_dept.get('abbreviation') or found_dept.get('name')
    elif matched_dept_alias:
        parsed['department_abbr'] = matched_dept_alias.upper()

    # 6. Extract College by Real DB Abbreviation (Highest Priority & Supports Shared Abbreviations)
    words_for_col = norm_text(raw).split()
    non_col_words = []
    matched_col_abbr = None
    abbr_map = taxonomy.get('abbr_to_colleges', {})

    for word in words_for_col:
        if word in abbr_map:
            matched_cols = abbr_map[word]
            matched_col_abbr = word.upper()
            for mc in matched_cols:
                if mc['id'] not in parsed['college_ids']:
                    parsed['college_ids'].append(mc['id'])

            # If user has client_college_id that matches one of the colleges with this abbreviation, select it
            if client_college_id and any(mc['id'] == client_college_id for mc in matched_cols):
                user_c = next(mc for mc in matched_cols if mc['id'] == client_college_id)
                parsed['college_name'] = user_c.get('name')
                parsed['college_id'] = user_c.get('id')
            elif len(matched_cols) == 1:
                parsed['college_name'] = matched_cols[0].get('name')
                parsed['college_id'] = matched_cols[0].get('id')
            else:
                # Multiple colleges have the exact same abbreviation!
                parsed['college_name'] = f"{word.upper()} ({len(matched_cols)} colleges)"
                parsed['college_id'] = matched_cols[0].get('id')
        else:
            non_col_words.append(word)

    if matched_col_abbr:
        parsed['college_abbr'] = matched_col_abbr

    raw = ' '.join(non_col_words)

    # 7. Extract College Multi-word Aliases & Single-word Aliases (Only if no real abbreviation matched)
    if not parsed['college_ids']:
        for ca in taxonomy.get('college_aliases', []):
            ca_alias = ca.get('alias_norm') or ''
            if ' ' in ca_alias and f" {ca_alias} " in f" {norm_text(raw)} ":
                if ca['college_id'] not in parsed['college_ids']:
                    parsed['college_ids'].append(ca['college_id'])
                if not parsed['college_name']:
                    for c in taxonomy.get('colleges', []):
                        if c['id'] == ca['college_id']:
                            parsed['college_name'] = c.get('name')
                            parsed['college_id'] = c.get('id')
                            break
                raw = re.sub(r'\b' + re.escape(ca_alias) + r'\b', ' ', raw, flags=re.IGNORECASE)

        words_for_ca = norm_text(raw).split()
        non_ca_words = []
        for word in words_for_ca:
            matched_ca_cols = [ca['college_id'] for ca in taxonomy.get('college_aliases', []) if word == ca.get('alias_norm')]
            if matched_ca_cols:
                for cid in matched_ca_cols:
                    if cid not in parsed['college_ids']:
                        parsed['college_ids'].append(cid)
                if not parsed['college_name']:
                    for c in taxonomy.get('colleges', []):
                        if c['id'] in matched_ca_cols:
                            parsed['college_name'] = c.get('name')
                            parsed['college_id'] = c.get('id')
                            break
            else:
                non_ca_words.append(word)
        raw = ' '.join(non_ca_words)

    # 8. Extract Author (e.g. 'by Rohit', 'author: John Doe')
    author_match = _AUTHOR_REGEX.search(raw)
    if author_match:
        matched_auth = author_match.group(1).strip()
        auth_words = matched_auth.split()
        if len(auth_words) > 1:
            second_word_norm = norm_text(auth_words[-1])
            if (second_word_norm in DEFAULT_DEPARTMENT_ALIASES or 
                any(second_word_norm == c.get('abbr_norm') for c in taxonomy.get('departments', [])) or 
                any(second_word_norm == norm_text(c.get('abbreviation')) for c in taxonomy.get('colleges', [])) or 
                any(second_word_norm == ca['alias_norm'] for ca in taxonomy.get('college_aliases', []))):
                matched_auth = ' '.join(auth_words[:-1])
        parsed['author'] = matched_auth
        raw = _AUTHOR_REGEX.sub(' ', raw)

    norm_q = norm_text(raw)
    remaining_words = norm_q.split()

    subject_search_str = ' '.join(remaining_words).strip()
    code_search_str = norm_code(subject_search_str)
    parsed['remaining_tokens'] = remaining_words

    if not subject_search_str:
        return parsed

    # 6. Tiered Subject Matching
    matched_candidates = []
    seen_subj_ids = set()
    matched_query_tokens = set()

    # Tier 1: Exact Normalized Code Match
    if code_search_str and len(code_search_str) >= 3:
        for s in taxonomy['subjects']:
            if s['code_norm'] == code_search_str:
                matched_candidates.append({
                    'subject': s,
                    'tier': 1,
                    'reason': f"Matched Code: {s.get('subject_code')}"
                })
                seen_subj_ids.add(s['id'])
                matched_query_tokens.add(s['code_norm'])
            else:
                for w in remaining_words:
                    if len(w) >= 3 and norm_code(w) == s['code_norm']:
                        matched_candidates.append({
                            'subject': s,
                            'tier': 1,
                            'reason': f"Matched Code: {s.get('subject_code')}"
                        })
                        seen_subj_ids.add(s['id'])
                        matched_query_tokens.add(norm_text(w))

    # Tier 2: Exact Alias / Acronym Match
    for a in taxonomy['subject_aliases']:
        an = a['alias_norm']
        if norm_text(subject_search_str) == an or subject_search_str.lower() == a['alias'].lower() or an in remaining_words:
            s_id = a['subject_id']
            if s_id not in seen_subj_ids:
                s = next((sub for sub in taxonomy['subjects'] if sub['id'] == s_id), None)
                if s:
                    matched_candidates.append({
                        'subject': s,
                        'tier': 2,
                        'reason': f"Matched Alias: {a['alias'].upper()} -> {s.get('name')}"
                    })
                    seen_subj_ids.add(s_id)
                    matched_query_tokens.add(an)

    # Tier 3: Exact or Prefix Subject Name Match
    clean_subj_q = norm_text(subject_search_str)
    for s in taxonomy['subjects']:
        if s['id'] in seen_subj_ids:
            continue
        if s['name_norm'] == clean_subj_q:
            matched_candidates.append({
                'subject': s,
                'tier': 3,
                'reason': f"Exact Subject: {s.get('name')}"
            })
            seen_subj_ids.add(s['id'])
            for tok in clean_subj_q.split(): matched_query_tokens.add(tok)
        elif s['name_norm'].startswith(clean_subj_q) and len(clean_subj_q) >= 4:
            matched_candidates.append({
                'subject': s,
                'tier': 3,
                'reason': f"Subject Prefix: {s.get('name')}"
            })
            seen_subj_ids.add(s['id'])
            for tok in clean_subj_q.split(): matched_query_tokens.add(tok)

    # Tier 4: Token Substring / Word Match
    if len(clean_subj_q) >= 3:
        for s in taxonomy['subjects']:
            if s['id'] in seen_subj_ids:
                continue
            if clean_subj_q in s['name_norm']:
                matched_candidates.append({
                    'subject': s,
                    'tier': 4,
                    'reason': f"Subject Match: {s.get('name')}"
                })
                seen_subj_ids.add(s['id'])

    # Tier 5: Fuzzy Matching via rapidfuzz (for typos like 'algorithem')
    if fuzz and not matched_candidates and len(clean_subj_q) >= 4:
        for s in taxonomy['subjects']:
            score = fuzz.token_sort_ratio(clean_subj_q, s['name_norm'])
            if score >= 75:
                matched_candidates.append({
                    'subject': s,
                    'tier': 5,
                    'reason': f"Fuzzy Match: {s.get('name')}"
                })
                seen_subj_ids.add(s['id'])

    # Derive topic tokens (residual words not consumed by subject matching)
    topic_tokens = [w for w in remaining_words if w not in matched_query_tokens and len(w) > 1]
    parsed['topic_tokens'] = topic_tokens
    parsed['topic_str'] = ' '.join(topic_tokens)
    parsed['exam_term'] = exam_term

    # Sort candidates by semester match then tier
    target_sem = parsed.get('semester')
    matched_candidates.sort(key=lambda x: (
        0 if (target_sem and get_subj_semester(x['subject']) == target_sem) else 1,
        x['tier']
    ))
    parsed['matched_subjects'] = matched_candidates
    if matched_candidates:
        parsed['match_reason'] = matched_candidates[0]['reason']

    return parsed

# -----------------------------------------------------------------------------
# 5. Core Search Execution with Graceful Relaxation
# -----------------------------------------------------------------------------
def execute_search_v3(
    query: str,
    college_id: str = None,
    department_id: str = None,
    semester: int = None,
    document_type: str = None,
    subject: str = None,
    year: str = None,
    author: str = None,
    sort: str = 'relevance',
    limit: int = 50
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Execute high-efficiency document search using in-memory intent parsing
    followed by an indexed document query and graceful relaxation.
    Supports keyword search, browse mode (empty query), and compound filters.
    """
    client = init_supabase()
    if not client:
        return [], {}

    taxonomy = get_taxonomy()
    parsed = parse_search_intent(query, client_college_id=college_id)

    # 1. Resolve College IDs
    target_college_ids = list(parsed['college_ids'])
    if not target_college_ids and college_id and college_id.upper() != 'ALL':
        if len(college_id) == 36:
            target_college_ids.append(college_id)
        else:
            c_norm = norm_text(college_id)
            for c in taxonomy['colleges']:
                if norm_text(c.get('abbreviation')) == c_norm or norm_text(c.get('name')) == c_norm or c_norm in norm_text(c.get('name')):
                    target_college_ids.append(c['id'])
                    break

    # 2. Resolve Department
    target_department_id = department_id or parsed.get('department_id')
    if target_department_id and len(str(target_department_id)) != 36:
        td_norm = norm_text(str(target_department_id))
        for d in taxonomy.get('departments', []):
            if d.get('abbr_norm') == td_norm or d.get('name_norm') == td_norm:
                target_department_id = d.get('id')
                break

    target_semester = semester or parsed['semester']
    target_category = document_type or parsed['category']
    target_year = year or parsed['year']
    target_author = author or parsed.get('author')

    matched_subj_ids = [m['subject']['id'] for m in parsed['matched_subjects']]

    # 3. Resolve Explicit Subject Filter (e.g. from dropdown)
    if subject and subject != 'All subjects':
        s_norm = norm_text(subject)
        for s in taxonomy['subjects']:
            if s['name_norm'] == s_norm or s_norm in s['name_norm']:
                if s['id'] not in matched_subj_ids:
                    matched_subj_ids.append(s['id'])
                    parsed['matched_subjects'].append({
                        'subject': s,
                        'tier': 1,
                        'reason': f"Selected Subject: {s.get('name')}"
                    })

    # 4. If semester specified but no subject, constrain to subjects of that semester
    if not matched_subj_ids and target_semester:
        sem_subj_ids = [s['id'] for s in taxonomy['subjects'] if get_subj_semester(s) == target_semester]
        if sem_subj_ids:
            matched_subj_ids = sem_subj_ids

    topic_str = parsed.get('topic_str', '')
    topic_tokens = parsed.get('topic_tokens', [])
    exam_term = parsed.get('exam_term')

    # Build structured chips representation
    chips = []
    if parsed.get('matched_subjects'):
        ms = parsed['matched_subjects'][0]['subject']
        chips.append({'type': 'subject', 'label': f"{ms.get('subject_code', '')} - {ms.get('name', '')}".strip(' -'), 'value': ms.get('id')})
    if parsed.get('college_name') or parsed.get('college_abbr'):
        chips.append({'type': 'college', 'label': parsed.get('college_abbr') or parsed.get('college_name'), 'value': parsed.get('college_id')})
    if parsed.get('department_abbr') or parsed.get('department_name'):
        chips.append({'type': 'branch', 'label': parsed.get('department_abbr') or parsed.get('department_name'), 'value': parsed.get('department_id')})
    if target_semester:
        chips.append({'type': 'semester', 'label': f"Sem {target_semester}", 'value': target_semester})
    if target_category and target_category != 'All types':
        chips.append({'type': 'type', 'label': target_category.title(), 'value': target_category})
    if target_year:
        chips.append({'type': 'year', 'label': str(target_year), 'value': target_year})
    if target_author:
        chips.append({'type': 'author', 'label': f"by {target_author}", 'value': target_author})

    residual_text = parsed.get('topic_str', '').strip()
    if not residual_text and not chips and query:
        residual_text = query.strip()

    meta: Dict[str, Any] = {
        'parsed': {
            'chips': chips,
            'residual_text': residual_text,
            'college_id': parsed.get('college_id') or (target_college_ids[0] if len(target_college_ids) == 1 else None),
            'college_ids': target_college_ids,
            'college_name': parsed.get('college_name'),
            'college_abbr': parsed.get('college_abbr'),
            'department_id': target_department_id,
            'department_name': parsed.get('department_name'),
            'department_abbr': parsed.get('department_abbr'),
            'semester': target_semester,
            'category': target_category,
            'year': target_year,
            'author': target_author,
            'subject': parsed['matched_subjects'][0]['subject']['name'] if parsed.get('matched_subjects') else None,
            'match_reason': parsed.get('match_reason')
        },
        'counts': {'exact': 0, 'close': 0, 'related': 0, 'total': 0},
        'did_you_mean': None,
        'fallback': None,
        'relaxed': False,
        'relaxation_message': None
    }

    # Typo correction & did_you_mean generation using search_vocab / rapidfuzz
    did_you_mean_query = None
    if fuzz and residual_text and len(residual_text) >= 4:
        vocab_list = taxonomy.get('vocab', [])
        corrected_words = []
        changed = False
        for word in residual_text.split():
            w_low = word.lower()
            if len(w_low) < 4 or w_low in {'for', 'and', 'the', 'iot', 'cse', 'it'}:
                corrected_words.append(word)
                continue
            best_match = None
            best_score = 0
            for v in vocab_list:
                v_term = v.get('term', '')
                if abs(len(v_term) - len(w_low)) <= 2:
                    score = fuzz.ratio(w_low, v_term)
                    if score > best_score and score >= 80:
                        best_score = score
                        best_match = v_term
            if best_match and best_match != w_low:
                corrected_words.append(best_match)
                changed = True
            else:
                corrected_words.append(word)
        if changed:
            did_you_mean_query = ' '.join(corrected_words)
            meta['did_you_mean'] = did_you_mean_query

    all_cached_docs = get_cached_documents()

    def fetch_documents_by_filter(c_ids, sub_ids, title_keyword=None, cat_filter=target_category, yr_filter=target_year):
        out = []
        kw_norm = norm_text(title_keyword) if title_keyword else ''
        for d in all_cached_docs:
            # 1. College constraint
            if c_ids:
                doc_cid = d.get('college_id') or (d.get('colleges') or {}).get('id')
                if doc_cid not in c_ids:
                    continue

            # 2. Department constraint
            if target_department_id and str(d.get('department_id')) != str(target_department_id):
                continue

            # 3. Category constraint
            if cat_filter and cat_filter != 'All types':
                tc = cat_filter.lower()
                doc_cat = (d.get('document_category') or '').lower()
                if 'note' in tc and doc_cat != 'notes':
                    continue
                elif ('paper' in tc or 'pyq' in tc or 'question' in tc or 'exam' in tc) and doc_cat not in ('papers', 'question_bank'):
                    continue
                elif ('practical' in tc or 'lab' in tc) and doc_cat != 'practical':
                    continue
                elif 'syllabus' in tc and doc_cat != 'syllabus':
                    continue
                elif 'timetable' in tc and doc_cat != 'timetable':
                    continue

            # 4. Year constraint
            if yr_filter:
                doc_yr = str(d.get('created_at', ''))[:4]
                doc_desc = (d.get('description') or '')
                if 'Year:' in doc_desc:
                    try:
                        doc_yr = doc_desc.split('Year:')[1].split('|')[0].strip()
                    except Exception:
                        pass
                if str(yr_filter) not in doc_yr:
                    continue

            # 5. Subject or Title match
            if sub_ids:
                if d.get('subject_id') not in sub_ids:
                    continue
            elif kw_norm:
                d_title_norm = d.get('title_norm') or norm_text(d.get('title'))
                d_search_text = d.get('search_text_norm') or norm_text(d.get('search_text') or '')
                if kw_norm not in d_title_norm and kw_norm not in d_search_text:
                    continue

            out.append(d)
            if len(out) >= limit:
                break
        return out

    # 1. Primary Database-side Tiered Search (Fast, index-driven RPC)
    docs_map = {}
    if query and len(query.strip()) >= 2:
        try:
            from methods.supabase_helper import search_documents_rpc
            primary_cid = target_college_ids[0] if target_college_ids and len(target_college_ids) == 1 else None
            primary_sid = matched_subj_ids[0] if matched_subj_ids and len(matched_subj_ids) == 1 else None
            rpc_results = search_documents_rpc(
                query=query.strip(),
                limit=limit * 2,
                college_id=primary_cid,
                department_id=target_department_id,
                subject_id=primary_sid,
                category=target_category if target_category != 'All types' else None,
                year=int(target_year) if target_year and str(target_year).isdigit() else None,
                status=['approved', 'pending']
            )
            if rpc_results:
                cached_by_id = {d['id']: d for d in all_cached_docs}
                for r in rpc_results:
                    r_id = r.get('id')
                    full_doc = dict(cached_by_id.get(r_id) or r)
                    full_doc['_rpc_score'] = r.get('score')
                    full_doc['_rpc_match_type'] = r.get('match_type')
                    docs_map[r_id] = full_doc
        except Exception as rpc_err:
            logger.warning(f"[SEARCH-RPC] Falling back to memory index: {rpc_err}")

    # 2. Dual Retrieval Fallback: by matched subjects AND by topic keywords in title
    if matched_subj_ids:
        subj_docs = fetch_documents_by_filter(target_college_ids, matched_subj_ids)
        for d in subj_docs:
            if d['id'] not in docs_map:
                docs_map[d['id']] = d

    # If user provided topic words (e.g. 'binary tree', 'deadlock'), fetch matching titles
    if topic_str and len(topic_str) >= 3 and len(docs_map) < limit:
        title_docs = fetch_documents_by_filter(target_college_ids, [], title_keyword=topic_str)
        for d in title_docs:
            if d['id'] not in docs_map and len(docs_map) < limit * 2:
                docs_map[d['id']] = d

    # Search individual topic tokens if compound title didn't catch everything
    for tok in (topic_tokens or []):
        if len(tok) >= 4 and len(docs_map) < limit:
            tok_docs = fetch_documents_by_filter(target_college_ids, [], title_keyword=tok)
            for d in tok_docs:
                if d['id'] not in docs_map and len(docs_map) < limit * 2:
                    docs_map[d['id']] = d

    # Fallback to general query if no docs found yet
    if not docs_map and query and len(query.strip()) >= 2:
        query_docs = fetch_documents_by_filter(target_college_ids, [], title_keyword=query.strip())
        for d in query_docs:
            docs_map[d['id']] = d

    # Critical fallback: if no documents fetched yet (empty query, browsing, or filter-only search)
    if not docs_map and (not query or matched_subj_ids):
        filter_docs = fetch_documents_by_filter(target_college_ids, matched_subj_ids)
        for d in filter_docs:
            docs_map[d['id']] = d

    # --- Fallback Ladder ---
    fallback_stage = 0
    relaxed_filters = []
    fallback_message = None

    # Stage 1: Typo tolerance via did_you_mean
    if not docs_map and did_you_mean_query:
        fallback_stage = 1
        relaxed_docs = fetch_documents_by_filter(target_college_ids, [], title_keyword=did_you_mean_query)
        for d in relaxed_docs:
            docs_map[d['id']] = d

    # Stage 2: Relax weakest filter in order: year -> semester -> type -> branch (preserve college)
    if not docs_map and (query or matched_subj_ids or target_year):
        subj_label = parsed['matched_subjects'][0]['subject']['name'] if parsed.get('matched_subjects') else "selected criteria"
        # 2a. Relax Year
        if target_year:
            relaxed_year_docs = fetch_documents_by_filter(target_college_ids, matched_subj_ids, yr_filter=None)
            for d in relaxed_year_docs:
                docs_map[d['id']] = d
            if docs_map:
                fallback_stage = 2
                relaxed_filters.append('year')
                fallback_message = f"No {target_year} files for {subj_label}. Showing other years."

        # 2b. Relax Semester
        if not docs_map and target_semester:
            relaxed_sem_docs = fetch_documents_by_filter(target_college_ids, [], title_keyword=query or None)
            for d in relaxed_sem_docs:
                docs_map[d['id']] = d
            if docs_map:
                fallback_stage = 2
                relaxed_filters.append('semester')
                fallback_message = f"No Sem {target_semester} files found. Showing other semesters."

        # 2c. Relax Resource Type
        if not docs_map and target_category and target_category != 'All types':
            relaxed_type_docs = fetch_documents_by_filter(target_college_ids, matched_subj_ids, title_keyword=query or None)
            for d in relaxed_type_docs:
                docs_map[d['id']] = d
            if docs_map:
                fallback_stage = 2
                relaxed_filters.append('type')
                fallback_message = f"No {target_category} files found. Showing all resource types."

    # Stage 3: Related files from same department/branch
    if not docs_map and target_department_id:
        dept_docs = fetch_documents_by_filter(target_college_ids, [])
        for d in dept_docs:
            if d.get('department_id') == target_department_id:
                docs_map[d['id']] = d
        if docs_map:
            fallback_stage = 3
            relaxed_filters.append('subject')
            fallback_message = "Related materials from your department."

    # Stage 4: Zero-result state (NEVER show random recent uploads when user typed a query!)
    if not docs_map:
        fallback_stage = 4
        fallback_message = "No exact matches found for your search."

    if fallback_stage > 0:
        meta['fallback'] = {
            'stage': fallback_stage,
            'relaxed_filters': relaxed_filters,
            'message': fallback_message
        }
        meta['relaxed'] = (fallback_stage == 2)
        meta['relaxation_message'] = fallback_message

    docs = list(docs_map.values())
    if target_author:
        author_clean = target_author.strip().lower()
        matched_author_docs = [
            d for d in docs
            if author_clean in ((d.get('profiles') or {}).get('full_name') or '').lower()
        ]
        if matched_author_docs:
            docs = matched_author_docs

    # Map database docs into unified frontend card structures with Multi-Factor Relevance Scoring
    results = []
    counts = {'exact': 0, 'close': 0, 'related': 0, 'total': 0}

    for doc in docs:
        subj = doc.get('subjects') or {}
        col = doc.get('colleges') or {}
        s_id = subj.get('id')
        subj_name = subj.get('name') or 'General'
        subj_code = (subj.get('subject_code') or '').strip()
        doc_title = doc.get('title') or ''
        doc_title_norm = norm_text(doc_title)
        doc_desc_raw = doc.get('description') or ''
        uploader_name = ((doc.get('profiles') or {}).get('full_name') or 'Anonymous').strip()

        score = 0.0
        reasons = []
        tier = 'related'

        clean_q = norm_text(query)
        code_q = norm_code(query)

        # 0. RPC Tier & Match Type integration
        rpc_sc = doc.get('_rpc_score')
        rpc_mt = doc.get('_rpc_match_type')
        if rpc_sc is not None:
            score += float(rpc_sc)
            if rpc_mt == 'code_exact':
                reasons.append({'field': 'subject_code', 'kind': 'exact', 'matched': f"Subject code matched"})
                tier = 'exact'
            elif rpc_mt == 'title_exact':
                reasons.append({'field': 'title', 'kind': 'exact', 'matched': f"Exact title: {doc_title}"})
                tier = 'exact'
            elif rpc_mt == 'title_prefix':
                reasons.append({'field': 'title', 'kind': 'prefix', 'matched': f"Title prefix: {doc_title}"})
                tier = 'close'
            elif rpc_mt == 'code_prefix':
                reasons.append({'field': 'subject_code', 'kind': 'prefix', 'matched': f"Code prefix matched"})
                tier = 'close'
            elif rpc_mt == 'fulltext':
                reasons.append({'field': 'title', 'kind': 'fulltext', 'matched': f"Keyword match: {doc_title}"})
                tier = 'close'
            elif rpc_mt in ('fuzzy_title', 'fuzzy_code'):
                reasons.append({'field': 'title', 'kind': 'fuzzy', 'matched': f"Typo-tolerant match: {doc_title}"})
                tier = 'related'
            else:
                reasons.append({'field': 'title', 'kind': 'match', 'matched': f"Matched: {doc_title}"})
                tier = 'related'

        # 1. Exact subject code match (+100)
        if subj_code and code_q and norm_code(subj_code) == code_q:
            score += 100.0
            reasons.append({'field': 'subject_code', 'kind': 'exact', 'matched': f"Code {subj_code} matched"})
            tier = 'exact'
        elif subj_code and any(norm_code(w) == norm_code(subj_code) for w in clean_q.split()):
            score += 100.0
            reasons.append({'field': 'subject_code', 'kind': 'exact', 'matched': f"Code {subj_code} matched"})
            tier = 'exact'

        # 2. Exact abbreviation or alias match (+90)
        for a in taxonomy.get('subject_aliases', []):
            if a['subject_id'] == s_id and (a['alias_norm'] == clean_q or a['alias_norm'] in clean_q.split()):
                score += 90.0
                reasons.append({'field': 'abbreviation', 'kind': 'alias', 'matched': f"Abbreviation {a['alias'].upper()} = {subj_name}"})
                tier = 'exact'
                break

        # 3. Exact phrase in title or subject name (+80)
        if clean_q and (clean_q == norm_text(subj_name) or clean_q in doc_title_norm):
            score += 80.0
            reasons.append({'field': 'title', 'kind': 'exact', 'matched': doc_title})
            if tier != 'exact':
                tier = 'exact'

        # 4. Word prefix match (+60)
        q_words = [w for w in clean_q.split() if len(w) > 2]
        if q_words and all(any(tw.startswith(qw) for tw in doc_title_norm.split()) for qw in q_words):
            score += 60.0
            reasons.append({'field': 'title', 'kind': 'prefix', 'matched': clean_q})
            if tier != 'exact':
                tier = 'close'

        # 5. Trigram / fuzzy similarity on title and subject name (up to +40)
        sim = 0.0
        if fuzz and clean_q:
            sim = fuzz.token_set_ratio(clean_q, doc_title_norm) / 100.0
            subj_sim = fuzz.token_set_ratio(clean_q, norm_text(subj_name)) / 100.0
            sim = max(sim, subj_sim)
            score += sim * 40.0
            if sim >= 0.70:
                if did_you_mean_query:
                    reasons.append({'field': 'subject_name', 'kind': 'fuzzy', 'matched': f"{subj_name} (typo corrected)"})
                else:
                    reasons.append({'field': 'title', 'kind': 'fuzzy', 'matched': doc_title})
                if tier not in ('exact',):
                    tier = 'close'
            elif sim >= 0.40:
                reasons.append({'field': 'title', 'kind': 'fuzzy', 'matched': doc_title})
                if tier not in ('exact', 'close'):
                    tier = 'related'

        # 6. Author match (+50)
        if target_author and target_author.strip().lower() in uploader_name.lower():
            score += 50.0
            reasons.append({'field': 'uploader', 'kind': 'exact', 'matched': f"Uploaded by {uploader_name}"})
            tier = 'exact'

        # 7. College match (+10)
        doc_col_id = doc.get('college_id') or col.get('id')
        if target_college_ids and doc_col_id in target_college_ids:
            score += 10.0
            c_name = col.get('name') or parsed.get('college_abbr') or "college"
            reasons.append({'field': 'college', 'kind': 'exact', 'matched': f"College {c_name}"})

        # 8. Semester and branch bonus (+8)
        if target_semester and get_subj_semester(subj) == target_semester:
            score += 8.0

        # 9. Popularity & Recency
        views = doc.get('view_count') or 0
        likes = doc.get('like_count') or 0
        score += min(8.0, math.log1p(views + 5 * likes))

        if not clean_q:
            tier = 'exact'
            score += 50.0

        if clean_q and score < 40.0 and sim < 0.30 and not reasons:
            continue

        primary_reason = reasons[0]['matched'] if reasons else ""

        is_paid = False
        price_val = 0.0
        doc_year = str(doc.get('created_at', ''))[:4] if doc.get('created_at') else ''
        try:
            if doc_desc_raw.startswith('{'):
                desc_json = json.loads(doc_desc_raw)
                pricing = desc_json.get('pricing', {})
                if isinstance(pricing, dict) and pricing.get('is_paid') and float(pricing.get('price', 0)) > 0:
                    is_paid = True
                    price_val = float(pricing.get('price', 0))
                if desc_json.get('year'):
                    doc_year = str(desc_json.get('year'))
            elif 'Year:' in doc_desc_raw:
                doc_year = doc_desc_raw.split('Year:')[1].split('|')[0].strip()
        except Exception:
            pass

        counts[tier] += 1
        counts['total'] += 1

        results.append({
            'record_id': doc.get('id'),
            'file-name': doc.get('title'),
            'file-path': doc.get('file_url'),
            'type': doc.get('document_category') or 'Papers',
            'file-type': doc.get('file_type') or 'pdf',
            'subject': subj_name,
            'subject_code': subj_code,
            'college': col.get('name') or '',
            'author': uploader_name,
            'view_count': views,
            'like_count': likes,
            'bookmark_count': doc.get('bookmark_count') or 0,
            'year': doc_year,
            'date': (doc.get('created_at') or '')[:10],
            'is_paid': is_paid,
            'price': price_val,
            'score': round(score, 2),
            'tier': tier,
            'match_reason': primary_reason,
            'match': {
                'tier': tier,
                'score': round(score, 2),
                'reasons': reasons
            }
        })

    meta['counts'] = counts

    if sort == 'views_desc':
        results.sort(key=lambda x: x['view_count'], reverse=True)
    elif sort == 'likes_desc':
        results.sort(key=lambda x: x['like_count'], reverse=True)
    elif sort == 'date_desc':
        results.sort(key=lambda x: x['date'], reverse=True)
    else:
        tier_weight = {'exact': 3, 'close': 2, 'related': 1}
        results.sort(key=lambda x: (tier_weight.get(x['tier'], 0), x['score']), reverse=True)

    return results[:limit], meta

# -----------------------------------------------------------------------------
# 6. Autocomplete Suggestions API (< 5ms in-memory)
# -----------------------------------------------------------------------------
def get_suggestions_payload(query: str, college_id: str = None) -> Dict[str, Any]:
    """Return structured autocomplete suggestions: detected intent row, grouped suggestions, and flat list."""
    if not query or len(query.strip()) < 1:
        return {'detected': None, 'groups': {'subjects': [], 'colleges': [], 'branches': [], 'uploaders': []}, 'suggestions': []}

    taxonomy = get_taxonomy()
    clean_q = norm_text(query)
    clean_code = norm_code(query)

    detected = None
    groups: Dict[str, List[Dict[str, Any]]] = {
        'subjects': [],
        'colleges': [],
        'branches': [],
        'uploaders': []
    }
    seen = set()

    # 1. Detected Intent Row (Exact resolution of code, alias, college, branch, or type)
    if clean_code:
        for s in taxonomy.get('subjects', []):
            if s['code_norm'] == clean_code:
                detected = {
                    'type': 'code',
                    'label': f"{s.get('subject_code')} as subject code",
                    'title': s.get('subject_code'),
                    'subtitle': s.get('name'),
                    'query': s.get('subject_code'),
                    'chip': {'type': 'subject', 'value': s.get('subject_code'), 'label': s.get('subject_code')}
                }
                break

    if not detected:
        for a in taxonomy.get('subject_aliases', []):
            if a['alias_norm'] == clean_q:
                s = next((sub for sub in taxonomy.get('subjects', []) if sub['id'] == a['subject_id']), None)
                if s:
                    detected = {
                        'type': 'alias',
                        'label': f"{a['alias'].upper()} as subject alias ({s.get('name')})",
                        'title': a['alias'].upper(),
                        'subtitle': s.get('name'),
                        'query': a['alias'].upper(),
                        'chip': {'type': 'subject', 'value': s.get('name'), 'label': a['alias'].upper()}
                    }
                    break

    if not detected:
        for c in taxonomy.get('colleges', []):
            c_abbr = norm_text(c.get('abbreviation'))
            if c_abbr and c_abbr == clean_q:
                detected = {
                    'type': 'college',
                    'label': f"{c.get('abbreviation')} as college",
                    'title': c.get('abbreviation'),
                    'subtitle': c.get('name'),
                    'query': c.get('abbreviation'),
                    'chip': {'type': 'college', 'value': c.get('id'), 'label': c.get('abbreviation')}
                }
                break

    if not detected:
        for d in taxonomy.get('departments', []):
            d_abbr = d.get('abbr_norm')
            if d_abbr and d_abbr == clean_q:
                lbl = d.get('abbreviation') or d.get('name')
                detected = {
                    'type': 'branch',
                    'label': f"{lbl} as branch",
                    'title': lbl,
                    'subtitle': d.get('name'),
                    'query': lbl,
                    'chip': {'type': 'branch', 'value': d.get('id'), 'label': lbl}
                }
                break

    # 2. Populate Group: Subjects (Codes, Aliases, Names)
    if clean_code:
        for s in taxonomy.get('subjects', []):
            if s['code_norm'].startswith(clean_code):
                val = f"{s.get('subject_code')} — {s.get('name')}"
                if val not in seen:
                    item = {
                        'type': 'code',
                        'title': s.get('subject_code'),
                        'subtitle': s.get('name'),
                        'query': s.get('subject_code'),
                        'chip': {'type': 'subject', 'value': s.get('subject_code'), 'label': s.get('subject_code')}
                    }
                    groups['subjects'].append(item)
                    seen.add(val)
                    if len(groups['subjects']) >= 4:
                        break

    if len(groups['subjects']) < 4:
        for a in taxonomy.get('subject_aliases', []):
            if a['alias_norm'].startswith(clean_q):
                s = next((sub for sub in taxonomy.get('subjects', []) if sub['id'] == a['subject_id']), None)
                if s:
                    val = f"{a['alias'].upper()} — {s.get('name')}"
                    if val not in seen:
                        item = {
                            'type': 'alias',
                            'title': a['alias'].upper(),
                            'subtitle': s.get('name'),
                            'query': a['alias'].upper(),
                            'chip': {'type': 'subject', 'value': s.get('name'), 'label': a['alias'].upper()}
                        }
                        groups['subjects'].append(item)
                        seen.add(val)
                        if len(groups['subjects']) >= 4:
                            break

    if len(groups['subjects']) < 4:
        for s in taxonomy.get('subjects', []):
            if s['name_norm'].startswith(clean_q) or (len(clean_q) >= 3 and clean_q in s['name_norm']):
                val = s.get('name')
                if val not in seen:
                    code_sub = f" ({s.get('subject_code')})" if s.get('subject_code') else ""
                    item = {
                        'type': 'subject',
                        'title': val,
                        'subtitle': f"Subject{code_sub}",
                        'query': val,
                        'chip': {'type': 'subject', 'value': val, 'label': val}
                    }
                    groups['subjects'].append(item)
                    seen.add(val)
                    if len(groups['subjects']) >= 4:
                        break

    # Group: Colleges
    for ca in taxonomy.get('college_aliases', []):
        if ca['alias_norm'].startswith(clean_q):
            c = next((col for col in taxonomy.get('colleges', []) if col['id'] == ca['college_id']), None)
            if c:
                val = c.get('name')
                if val not in seen:
                    item = {
                        'type': 'college',
                        'title': ca['alias'].upper(),
                        'subtitle': val,
                        'query': ca['alias'].upper(),
                        'chip': {'type': 'college', 'value': c.get('id'), 'label': ca['alias'].upper()}
                    }
                    groups['colleges'].append(item)
                    seen.add(val)
                    if len(groups['colleges']) >= 4:
                        break

    if len(groups['colleges']) < 4:
        for col in taxonomy.get('colleges', []):
            c_abbr = norm_text(col.get('abbreviation'))
            c_name = norm_text(col.get('name'))
            if (c_abbr and c_abbr.startswith(clean_q)) or (len(clean_q) >= 3 and clean_q in c_name):
                val = col.get('name')
                if val not in seen:
                    title_lbl = (col.get('abbreviation') or val).strip()
                    item = {
                        'type': 'college',
                        'title': title_lbl,
                        'subtitle': val.strip(),
                        'query': title_lbl,
                        'chip': {'type': 'college', 'value': col.get('id'), 'label': title_lbl}
                    }
                    groups['colleges'].append(item)
                    seen.add(val)
                    if len(groups['colleges']) >= 4:
                        break

    # Group: Branches / Departments
    for d in taxonomy.get('departments', []):
        d_abbr = d.get('abbr_norm') or ''
        d_name = d.get('name_norm') or ''
        if (d_abbr and d_abbr.startswith(clean_q)) or (len(clean_q) >= 3 and clean_q in d_name):
            val = d.get('name')
            if val not in seen:
                lbl = (d.get('abbreviation') or val).strip()
                item = {
                    'type': 'branch',
                    'title': lbl,
                    'subtitle': val.strip(),
                    'query': lbl,
                    'chip': {'type': 'branch', 'value': d.get('id'), 'label': lbl}
                }
                groups['branches'].append(item)
                seen.add(val)
                if len(groups['branches']) >= 4:
                    break

    # Document title autocomplete via RPC
    groups['documents'] = []
    if len(clean_q) >= 2:
        try:
            from methods.supabase_helper import suggest_documents_rpc
            doc_suggs = suggest_documents_rpc(clean_q, limit=4, status=['approved', 'pending'])
            for ds in (doc_suggs or []):
                t = ds.get('suggestion')
                c = ds.get('doc_count')
                if t and t not in seen:
                    item = {
                        'type': 'document',
                        'title': t,
                        'subtitle': f"{c} document{'s' if c != 1 else ''}",
                        'query': t,
                        'chip': {'type': 'title', 'value': t, 'label': t}
                    }
                    groups['documents'].append(item)
                    seen.add(t)
        except Exception:
            pass

    # Flattened suggestions list for dropdowns
    all_suggestions: List[Dict[str, Any]] = []
    if detected:
        all_suggestions.append(detected)
    for g in ['subjects', 'documents', 'colleges', 'branches', 'uploaders']:
        for it in groups.get(g, []):
            if it not in all_suggestions:
                all_suggestions.append(it)

    return {
        'detected': detected,
        'groups': groups,
        'suggestions': all_suggestions
    }

def get_suggestions(query: str, college_id: str = None, limit: int = 8) -> List[Dict[str, Any]]:
    """Instant in-memory suggestions for subject codes, aliases, names, and colleges."""
    payload = get_suggestions_payload(query, college_id=college_id)
    return payload.get('suggestions', [])[:limit]

# -----------------------------------------------------------------------------
# 7. Flask HTTP Endpoints
# -----------------------------------------------------------------------------
def suggest_endpoint():
    """Fast, lightweight autocomplete endpoint with detected intent & grouped categories."""
    q = request.args.get('q', '').strip()
    college_id = request.args.get('college_id')
    payload = get_suggestions_payload(q, college_id=college_id)
    return jsonify({
        'success': True,
        'detected': payload.get('detected'),
        'groups': payload.get('groups', {}),
        'suggestions': payload.get('suggestions', [])
    })

def search_v2_endpoint():
    """Unified Search Endpoint with tiered resolution and relaxation."""
    q = request.args.get('q', '').strip()
    college_id = request.args.get('college_id')
    department_id = request.args.get('department_id') or request.args.get('branch')
    semester = request.args.get('semester') or request.args.get('sem')
    document_type = request.args.get('document_type') or request.args.get('type')
    subject = request.args.get('subject')
    year = request.args.get('year')
    author = request.args.get('author')
    sort = request.args.get('sort', 'relevance')

    try:
        sem_int = int(semester) if semester and str(semester).isdigit() else None
    except Exception:
        sem_int = None

    # Quota enforcement via session counter (avoids synchronous DB hit on every search)
    try:
        from methods.scoring_engine import get_feature_gate
        from flask import session as _session
        uid = _session.get('user', {}).get('uid')
        if uid and q:
            gate = get_feature_gate(uid)
            daily_limit = gate.get('daily_searches', 100)
            session_key = f'_sq_{uid}'
            search_count = _session.get(session_key, 0)
            if search_count >= daily_limit:
                return jsonify({
                    'success': False,
                    'message': f"Daily search limit reached ({daily_limit}/day for your level). Contribute to level up!",
                    'quota_exceeded': True
                }), 429
            _session[session_key] = search_count + 1
            _session.modified = True
    except Exception as quota_err:
        logger.warning(f"[GATING] search quota check skipped: {quota_err}")


    results, meta = execute_search_v3(
        query=q,
        college_id=college_id,
        department_id=department_id,
        semester=sem_int,
        document_type=document_type,
        subject=subject,
        year=year,
        author=author,
        sort=sort
    )

    return jsonify({
        'success': True,
        'count': len(results),
        'results': results,
        'meta': meta
    })

def search_analytics_endpoint():
    """Log search analytics and zero-result queries for dictionary expansion."""
    try:
        data = request.get_json(silent=True) or {}
        query = data.get('query', '').strip()
        results_count = data.get('results_count', 0)

        if query:
            from methods.supabase_helper import init_supabase_admin
            client = init_supabase_admin() or init_supabase()
            if client:
                try:
                    client.table('search_analytics').insert({
                        'query': query,
                        'results_count': results_count
                    }).execute()
                except Exception as insert_err:
                    logger.warning(f"[SEARCH_ANALYTICS] Insert skipped/suppressed: {insert_err}")

                try:
                    from flask import session as _session
                    from methods.scoring_engine import process_event
                    uid = _session.get('user', {}).get('uid')
                    if uid:
                        process_event(
                            user_id=uid,
                            event_type='search_performed',
                            entity_id=None,
                            entity_type='search',
                            description=f'Searched: {query[:80]}',
                        )
                except Exception as se_err:
                    logger.warning(f"[SCORING] search event skipped: {se_err}")

        return ('', 204)
    except Exception as e:
        logger.warning(f"[SEARCH_ANALYTICS] Suppressed error: {e}")
        return ('', 204)

# Backward compatibility alias
execute_search = lambda q, college_id=None, limit=50: execute_search_v3(q, college_id=college_id, limit=limit)[0]
