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

            # 2. Departments
            dept_res = client.table('departments').select('id, name, abbreviation').execute()
            departments = dept_res.data or []

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

            _TAXONOMY_CACHE = {
                'colleges': colleges,
                'departments': departments,
                'subjects': subjects,
                'subject_aliases': subject_aliases,
                'college_aliases': college_aliases,
                'last_updated': time.time()
            }
        except Exception as e:
            logger.error(f"[Search Taxonomy] Error reloading taxonomy: {e}")

    return _TAXONOMY_CACHE

# -----------------------------------------------------------------------------
# 4. In-Memory Query Parser (< 1ms)
# -----------------------------------------------------------------------------
_SEM_REGEX = re.compile(r'\b(?:sem(?:ester)?|s)\s*([1-8])\b|\b([1-8])(?:st|nd|rd|th)\s*sem(?:ester)?\b', re.IGNORECASE)
_YEAR_REGEX = re.compile(r'\b(201[5-9]|202[0-9])\b')
_CATEGORY_REGEX = re.compile(r'\b(pyqs?|previous year|question papers?|notes?|practicals?|lab manuals?|syllabus)\b', re.IGNORECASE)

def parse_search_intent(query: str, client_college_id: str = None) -> Dict[str, Any]:
    """Parse user query in memory to resolve entities, filters, and subject keywords."""
    taxonomy = get_taxonomy()
    parsed: Dict[str, Any] = {
        'original_query': query,
        'college_ids': [],
        'college_name': None,
        'semester': None,
        'category': None,
        'year': None,
        'remaining_tokens': [],
        'matched_subjects': [],
        'match_reason': None
    }

    if client_college_id and client_college_id.upper() != 'ALL' and len(client_college_id) == 36:
        parsed['college_ids'].append(client_college_id)

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

    # 5. Extract College Alias from query
    norm_q = norm_text(raw)
    words = norm_q.split()
    remaining_words = []

    for word in words:
        found_college = False
        for ca in taxonomy['college_aliases']:
            if word == ca['alias_norm']:
                if ca['college_id'] not in parsed['college_ids']:
                    parsed['college_ids'].append(ca['college_id'])
                if not parsed['college_name']:
                    # Look up official name
                    for c in taxonomy['colleges']:
                        if c['id'] == ca['college_id']:
                            parsed['college_name'] = c.get('name')
                            break
                found_college = True
                break
        if not found_college:
            # Check college abbreviations directly (VNIT, GHRCE, PCE, etc.)
            for c in taxonomy['colleges']:
                if c.get('abbreviation') and word == norm_text(c.get('abbreviation')):
                    if c['id'] not in parsed['college_ids']:
                        parsed['college_ids'].append(c['id'])
                    if not parsed['college_name']:
                        parsed['college_name'] = c.get('name')
                    found_college = True
                    break
        if not found_college:
            remaining_words.append(word)

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

    target_semester = semester or parsed['semester']
    target_category = document_type or parsed['category']
    target_year = year or parsed['year']

    matched_subj_ids = [m['subject']['id'] for m in parsed['matched_subjects']]

    # 2. Resolve Explicit Subject Filter (e.g. from dropdown)
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

    # 3. If semester specified but no subject, constrain to subjects of that semester
    if not matched_subj_ids and target_semester:
        sem_subj_ids = [s['id'] for s in taxonomy['subjects'] if get_subj_semester(s) == target_semester]
        if sem_subj_ids:
            matched_subj_ids = sem_subj_ids

    topic_str = parsed.get('topic_str', '')
    topic_tokens = parsed.get('topic_tokens', [])
    exam_term = parsed.get('exam_term')

    meta: Dict[str, Any] = {
        'parsed': {
            'college_name': parsed['college_name'],
            'semester': target_semester,
            'category': target_category,
            'year': target_year,
            'match_reason': parsed['match_reason']
        },
        'relaxed': False,
        'relaxation_message': None
    }

    def fetch_documents_by_filter(c_ids, sub_ids, title_keyword=None):
        q = client.table('documents').select(
            'id, title, file_url, document_category, file_type, '
            'view_count, like_count, bookmark_count, created_at, description, '
            'profiles!documents_uploader_id_fkey(full_name), '
            'subjects(id, name, subject_code, semester), colleges(id, name)'
        ).eq('status', 'approved')

        if c_ids:
            if len(c_ids) == 1:
                q = q.eq('college_id', c_ids[0])
            else:
                q = q.in_('college_id', c_ids)

        if department_id and len(department_id) == 36:
            q = q.eq('department_id', department_id)

        # Robust case-insensitive category matching
        if target_category and target_category != 'All types':
            tc = target_category.lower()
            if 'note' in tc:
                q = q.eq('document_category', 'notes')
            elif 'paper' in tc or 'pyq' in tc or 'question' in tc or 'exam' in tc:
                q = q.in_('document_category', ['papers', 'question_bank'])
            elif 'practical' in tc or 'lab' in tc:
                q = q.eq('document_category', 'practical')
            elif 'syllabus' in tc:
                q = q.eq('document_category', 'syllabus')
            elif 'timetable' in tc:
                q = q.eq('document_category', 'timetable')
            else:
                q = q.ilike('document_category', f'%{tc}%')

        if sub_ids:
            q = q.in_('subject_id', sub_ids)
        elif title_keyword and len(title_keyword) >= 2:
            q = q.ilike('title', f'%{title_keyword}%')

        return q.order('created_at', desc=True).limit(limit).execute().data or []

    # 1. Dual Retrieval: by matched subjects AND by topic keywords in title
    docs_map = {}
    if matched_subj_ids:
        subj_docs = fetch_documents_by_filter(target_college_ids, matched_subj_ids)
        for d in subj_docs:
            docs_map[d['id']] = d

    # If user provided topic words (e.g. 'binary tree', 'deadlock'), fetch matching titles
    if topic_str and len(topic_str) >= 3:
        title_docs = fetch_documents_by_filter(target_college_ids, [], title_keyword=topic_str)
        for d in title_docs:
            if d['id'] not in docs_map:
                docs_map[d['id']] = d

    # Search individual topic tokens if compound title didn't catch everything
    for tok in (topic_tokens or []):
        if len(tok) >= 4 and len(docs_map) < limit:
            tok_docs = fetch_documents_by_filter(target_college_ids, [], title_keyword=tok)
            for d in tok_docs:
                if d['id'] not in docs_map:
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

    # 2. Graceful Relaxation Step 1: Relax College Filter if empty
    if not docs_map and target_college_ids:
        relaxed_docs = fetch_documents_by_filter([], matched_subj_ids)
        for d in relaxed_docs:
            docs_map[d['id']] = d
        if docs_map:
            meta['relaxed'] = True
            c_label = parsed['college_name'] or "your college"
            meta['relaxation_message'] = f"No documents found at {c_label}. Showing matching resources from other universities."

    # 3. Graceful Relaxation Step 2: Fallback to general title keywords if subject matching had no uploads
    if not docs_map and query:
        fallback_docs = fetch_documents_by_filter([], [], title_keyword=query)
        for d in fallback_docs:
            docs_map[d['id']] = d
        if docs_map:
            meta['relaxed'] = True
            meta['relaxation_message'] = f"Showing documents matching keyword '{query}'."

    # 4. Final Fallback: if filters returned 0, fetch latest approved docs so user never sees a broken blank page
    if not docs_map:
        latest_docs = fetch_documents_by_filter([], [])
        for d in latest_docs:
            docs_map[d['id']] = d
        if docs_map:
            meta['relaxed'] = True
            meta['relaxation_message'] = "No exact matches for chosen filters. Showing recent uploaded study material."

    docs = list(docs_map.values())

    # Map database docs into unified frontend card structures with Multi-Factor Relevance Scoring
    results = []
    subject_tier_map = {m['subject']['id']: (m['tier'], m['reason']) for m in parsed['matched_subjects']}

    for doc in docs:
        subj = doc.get('subjects') or {}
        col = doc.get('colleges') or {}
        s_id = subj.get('id')
        subj_name = subj.get('name') or 'General'

        tier_info = subject_tier_map.get(s_id, (4, f"Keyword: {doc.get('title')}"))
        doc_tier = tier_info[0]
        match_reason = tier_info[1]

        # Multi-factor relevance scoring
        base_score = 100 - (doc_tier * 12)  # Tier 1=88, Tier 2=76, Tier 3=64, Tier 4=52

        doc_title = doc.get('title') or ''
        doc_title_norm = norm_text(doc_title)
        doc_desc_raw = doc.get('description') or ''
        doc_desc_norm = norm_text(doc_desc_raw)

        # Topic & Sub-topic Bonus (with plural / stem support)
        topic_bonus = 0.0
        if topic_str and topic_str in doc_title_norm:
            topic_bonus += 50.0
            match_reason = f"Matched Topic: {doc_title}"
        elif topic_tokens:
            def matches_tok(t, text):
                return t in text or (len(t) > 3 and (t[:-1] in text or (t + 's') in text))

            token_matches = [t for t in topic_tokens if matches_tok(t, doc_title_norm)]
            if len(token_matches) == len(topic_tokens):
                topic_bonus += 40.0
                match_reason = f"Matched Topic: {doc_title}"
            elif token_matches:
                topic_bonus += 18.0 * len(token_matches)
            else:
                desc_matches = [t for t in topic_tokens if matches_tok(t, doc_desc_norm)]
                if desc_matches:
                    topic_bonus += 12.0 * len(desc_matches)

        # Exam Term Bonus (Midsem <-> CAE1/2/MST, Endsem <-> ESE)
        exam_bonus = 0.0
        if exam_term:
            equivs = EXAM_EQUIVALENCES.get(exam_term, [exam_term])
            matched_eq = next((eq for eq in equivs if eq in doc_title_norm), None)
            if matched_eq:
                exam_bonus += 35.0
                match_reason = f"Matched Exam: {exam_term.upper()} -> {doc_title}"
            else:
                desc_eq = next((eq for eq in equivs if eq in doc_desc_norm), None)
                if desc_eq:
                    exam_bonus += 18.0

        # Semester Match Bonus
        semester_bonus = 0.0
        if target_semester:
            subj_sem = get_subj_semester(subj)
            if subj_sem and int(subj_sem) == int(target_semester):
                semester_bonus += 35.0
                match_reason += f" (Sem {target_semester})"
            elif f"semester {target_semester}" in doc_desc_norm or f"sem {target_semester}" in doc_desc_norm:
                semester_bonus += 20.0

        # College Match Bonus
        college_bonus = 0.0
        if target_college_ids:
            doc_col_id = doc.get('college_id') or col.get('id')
            if doc_col_id in target_college_ids:
                college_bonus += 20.0

        # Subject Code in Title Bonus
        code_bonus = 0.0
        subj_code_clean = norm_code(subj.get('subject_code'))
        if subj_code_clean and len(subj_code_clean) >= 4 and subj_code_clean in norm_code(doc_title):
            code_bonus += 20.0

        # Category Bonus
        category_bonus = 0.0
        doc_cat = (doc.get('document_category') or '').lower()
        if target_category:
            tc = target_category.lower()
            if tc in doc_cat or (tc == 'papers' and 'bank' in doc_cat):
                category_bonus += 25.0

        # Parse year and price from description
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

        # Year Bonus
        year_bonus = 0.0
        if target_year and str(target_year) == str(doc_year):
            year_bonus += 30.0

        # Popularity Tie-Breaker (strictly capped to max 5 pts)
        views = doc.get('view_count') or 0
        likes = doc.get('like_count') or 0
        pop_bonus = min(5.0, 0.5 * math.log1p(views) + 1.0 * math.log1p(likes))

        final_score = base_score + topic_bonus + exam_bonus + category_bonus + semester_bonus + college_bonus + code_bonus + year_bonus + pop_bonus


        results.append({
            'record_id': doc.get('id'),
            'file-name': doc.get('title'),
            'file-path': doc.get('file_url'),
            'type': doc.get('document_category') or 'Papers',
            'file-type': doc.get('file_type') or 'pdf',
            'subject': subj_name,
            'subject_code': subj.get('subject_code') or '',
            'college': col.get('name') or '',
            'author': (doc.get('profiles') or {}).get('full_name') or 'Anonymous',
            'view_count': views,
            'like_count': likes,
            'bookmark_count': doc.get('bookmark_count') or 0,
            'year': doc_year,
            'date': (doc.get('created_at') or '')[:10],
            'is_paid': is_paid,
            'price': price_val,
            'score': round(final_score, 2),
            'tier': doc_tier,
            'match_reason': match_reason
        })

    # Sort results
    if sort == 'views_desc':
        results.sort(key=lambda x: x['view_count'], reverse=True)
    elif sort == 'likes_desc':
        results.sort(key=lambda x: x['like_count'], reverse=True)
    elif sort == 'date_desc':
        results.sort(key=lambda x: x['date'], reverse=True)
    else:
        # Relevance: strictly highest final_score first
        results.sort(key=lambda x: -x['score'])

    return results[:limit], meta

# -----------------------------------------------------------------------------
# 6. Autocomplete Suggestions API (< 5ms in-memory)
# -----------------------------------------------------------------------------
def get_suggestions(query: str, college_id: str = None, limit: int = 8) -> List[Dict[str, str]]:
    """Instant in-memory suggestions for subject codes, aliases, names, and colleges."""
    if not query or len(query.strip()) < 1:
        return []

    taxonomy = get_taxonomy()
    clean_q = norm_text(query)
    clean_code = norm_code(query)
    suggestions: List[Dict[str, str]] = []
    seen = set()

    # 1. Subject code matches
    if clean_code:
        for s in taxonomy['subjects']:
            if s['code_norm'].startswith(clean_code):
                val = f"{s.get('subject_code')} — {s.get('name')}"
                if val not in seen:
                    suggestions.append({'type': 'code', 'title': s.get('subject_code'), 'subtitle': s.get('name'), 'query': s.get('subject_code')})
                    seen.add(val)
                    if len(suggestions) >= limit: return suggestions

    # 2. Alias matches (OS, DBMS, etc.)
    for a in taxonomy['subject_aliases']:
        if a['alias_norm'].startswith(clean_q):
            s = next((sub for sub in taxonomy['subjects'] if sub['id'] == a['subject_id']), None)
            if s:
                val = f"{a['alias'].upper()} — {s.get('name')}"
                if val not in seen:
                    suggestions.append({'type': 'alias', 'title': a['alias'].upper(), 'subtitle': s.get('name'), 'query': a['alias'].upper()})
                    seen.add(val)
                    if len(suggestions) >= limit: return suggestions

    # 3. Subject name prefix matches
    for s in taxonomy['subjects']:
        if s['name_norm'].startswith(clean_q) or clean_q in s['name_norm']:
            val = s.get('name')
            if val not in seen:
                code_sub = f" ({s.get('subject_code')})" if s.get('subject_code') else ""
                suggestions.append({'type': 'subject', 'title': val, 'subtitle': f"Subject{code_sub}", 'query': val})
                seen.add(val)
                if len(suggestions) >= limit: return suggestions

    # 4. College matches
    for ca in taxonomy['college_aliases']:
        if ca['alias_norm'].startswith(clean_q):
            c = next((col for col in taxonomy['colleges'] if col['id'] == ca['college_id']), None)
            if c:
                val = c.get('name')
                if val not in seen:
                    suggestions.append({'type': 'college', 'title': ca['alias'].upper(), 'subtitle': val, 'query': ca['alias'].upper()})
                    seen.add(val)
                    if len(suggestions) >= limit: return suggestions

    for col in taxonomy['colleges']:
        c_abbr = norm_text(col.get('abbreviation'))
        c_name = norm_text(col.get('name'))
        if (c_abbr and c_abbr.startswith(clean_q)) or (len(clean_q) >= 3 and clean_q in c_name):
            val = col.get('name')
            if val not in seen:
                title_lbl = col.get('abbreviation') or val
                suggestions.append({'type': 'college', 'title': title_lbl.strip(), 'subtitle': val.strip(), 'query': title_lbl.strip()})
                seen.add(val)
                if len(suggestions) >= limit: return suggestions

    return suggestions[:limit]

# -----------------------------------------------------------------------------
# 7. Flask HTTP Endpoints
# -----------------------------------------------------------------------------
def suggest_endpoint():
    """Fast, lightweight autocomplete endpoint."""
    q = request.args.get('q', '').strip()
    college_id = request.args.get('college_id')
    return jsonify({
        'success': True,
        'suggestions': get_suggestions(q, college_id=college_id)
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
    sort = request.args.get('sort', 'relevance')

    try:
        sem_int = int(semester) if semester and str(semester).isdigit() else None
    except Exception:
        sem_int = None

    # Access-level search quota enforcement
    try:
        from methods.scoring_engine import get_feature_gate
        from flask import session as _session
        uid = _session.get('user', {}).get('uid')
        if uid and q:
            gate = get_feature_gate(uid)
            client = init_supabase()
            from datetime import datetime, timedelta, timezone
            since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            used = client.table('contribution_logs').select('id') \
                .eq('user_id', uid).eq('action_type', 'search_performed') \
                .gte('created_at', since).limit(gate['daily_searches'] + 1).execute()
            if len(used.data or []) >= gate['daily_searches']:
                return jsonify({
                    'success': False,
                    'message': f"Daily search limit reached ({gate['daily_searches']}/day for your level). Contribute to level up!",
                    'quota_exceeded': True
                }), 429
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
        data = request.get_json() or {}
        query = data.get('query', '').strip()
        results_count = data.get('results_count', 0)
        relaxed = data.get('relaxed', False)

        if query:
            client = init_supabase()
            if client:
                client.table('search_analytics').insert({
                    'query': query,
                    'results_count': results_count
                }).execute()

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

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Backward compatibility alias
execute_search = lambda q, college_id=None, limit=50: execute_search_v3(q, college_id=college_id, limit=limit)[0]
