"""
Timetable-Based Exam Recommendation Engine for AbhiHub.
Provides personalized document recommendations aligned with upcoming university examination schedules.
Timezone: Asia/Kolkata.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import zoneinfo

import re
from urllib.parse import quote
from methods.supabase_helper import init_supabase, init_supabase_admin, get_peer_recommended_files

KOLKATA_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")

def get_current_kolkata_date() -> datetime:
    """Returns current datetime in Asia/Kolkata timezone."""
    return datetime.now(KOLKATA_TZ)

def calculate_file_exam_match_score(doc: dict, exam: dict) -> float:
    """
    Ranks a document for a specific exam:
    1. PYQ / Question Papers first, then Notes.
    2. Most recent files first (by year / created_at).
    3. Quality score (likes, views) as secondary tie-breakers.
    """
    score = 0.0
    exam_type = (exam.get('exam_type') or 'THEORY').upper()
    doc_cat = (doc.get('document_category') or '').lower()
    doc_title = (doc.get('title') or '').lower()

    # 1. Tier Priority:
    # For PRACTICAL exams: lab manuals/viva first; For THEORY exams: PYQ first, then notes
    if exam_type == 'PRACTICAL':
        if doc_cat in ['practical'] or any(w in doc_title or w in doc_cat for w in ['practical', 'lab', 'manual', 'viva', 'experiment', 'code']):
            score += 250.0
        elif doc_cat in ['papers', 'pyq']:
            score += 50.0
        elif doc_cat in ['notes']:
            score += 30.0
        else:
            score += 10.0
    else:
        # THEORY / ESE exams: PYQ/Papers first (200), Notes second (100), others third (30)
        if doc_cat in ['papers', 'pyq', 'question_banks'] or any(w in doc_title for w in ['pyq', 'question paper', 'paper', 'previous year', 'solved paper']):
            score += 200.0
        elif doc_cat in ['notes'] or any(w in doc_title for w in ['note', 'handwritten', 'module', 'unit', 'formula']):
            score += 100.0
        else:
            score += 30.0

    # 2. Recency boost (most recent year first)
    doc_year = None
    year_match = re.search(r'\b(202[0-9])\b', doc_title)
    if year_match:
        try:
            doc_year = int(year_match.group(1))
        except ValueError:
            pass
    if not doc_year and doc.get('created_at'):
        try:
            doc_year = int(str(doc['created_at'])[:4])
        except (ValueError, TypeError):
            pass

    if doc_year:
        if doc_year >= 2026:
            score += 40.0
        elif doc_year == 2025:
            score += 30.0
        elif doc_year == 2024:
            score += 20.0
        elif doc_year == 2023:
            score += 10.0

    # Created_at sub-ranking for newer uploads
    if doc.get('created_at'):
        try:
            c_date = datetime.fromisoformat(str(doc['created_at']).replace('Z', '+00:00'))
            age_days = (datetime.now(timezone.utc) - c_date).days
            score += max(0.0, min(15.0, 15.0 - (age_days * 0.05)))
        except Exception:
            pass

    # 3. Proximity score
    days_left = exam.get('days_until_exam', 30)
    if days_left <= 0:
        score += 50.0
    elif days_left <= 3:
        score += 40.0
    elif days_left <= 7:
        score += 30.0
    elif days_left <= 14:
        score += 20.0
    elif days_left <= 30:
        score += 10.0

    # 4. Quality score (views and likes)
    likes = int(doc.get('like_count') or 0)
    views = int(doc.get('view_count') or 0)
    score += min(15.0, (likes * 1.5) + (views * 0.02))

    return score

def get_exam_based_recommendations(user_id: Optional[str] = None, limit_per_exam: int = 4) -> Dict:
    """
    Returns upcoming, today's, and recently completed exam schedules and ranked file recommendations for the user.
    Prioritizes:
    1. PYQ / Previous Year Papers (recent years first)
    2. Notes & Topper Guides (recent first)
    3. Post-exam question paper upload prompt for completed exams.
    """
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'source': 'fallback', 'exams': [], 'recommended_files': []}

    now_kolkata = get_current_kolkata_date()
    today_str = now_kolkata.strftime('%Y-%m-%d')
    past_7_days_str = (now_kolkata - timedelta(days=7)).strftime('%Y-%m-%d')
    future_limit_str = (now_kolkata + timedelta(days=45)).strftime('%Y-%m-%d')

    user_profile = None
    if user_id:
        try:
            p_res = client.table('profiles').select(
                'id, college_id, department_id, semester, section'
            ).eq('id', user_id).limit(1).execute()
            if p_res.data:
                user_profile = p_res.data[0]
        except Exception as e:
            logging.warning(f"[ExamRecommender] Failed to load profile: {e}")

    # Fall back if no semester info
    user_sem = str(user_profile.get('semester') or '').strip().upper() if user_profile else ''
    if not user_sem and user_profile:
        user_sem = 'FIRST'

    if not user_sem:
        peer_doc_ids = get_peer_recommended_files(user_id=user_id, limit=8) if user_id else []
        return {
            'source': 'peer_fallback',
            'exams': [],
            'peer_doc_ids': peer_doc_ids,
            'message': 'Profile incomplete (semester missing); using peer recommendations.'
        }

    department_id = user_profile.get('department_id') if user_profile else None
    user_sec = str(user_profile.get('section', '')).strip().upper() if (user_profile and user_profile.get('section')) else None

    # Resolve matching department IDs (e.g. AI matches Artificial Intelligence, CSE (AI), etc.)
    target_dept_ids = []
    if department_id:
        target_dept_ids.append(department_id)
        try:
            dept_res = client.table('departments').select('id, name, abbreviation').execute().data or []
            user_dept = next((d for d in dept_res if d['id'] == department_id), None)
            if user_dept:
                abbr = (user_dept.get('abbreviation') or '').lower()
                name = (user_dept.get('name') or '').lower()
                for d in dept_res:
                    d_abbr = (d.get('abbreviation') or '').lower()
                    d_name = (d.get('name') or '').lower()
                    if abbr and (abbr in d_abbr or abbr in d_name):
                        target_dept_ids.append(d['id'])
                    elif ('artificial' in name and 'artificial' in d_name) or ('computer' in name and 'computer' in d_name):
                        target_dept_ids.append(d['id'])
            
            # If First Year, include First Year / All Branches common departments
            if user_sem in ['FIRST', 'I', '1']:
                for d in dept_res:
                    if 'first year' in (d.get('name') or '').lower() or 'all branches' in (d.get('name') or '').lower():
                        target_dept_ids.append(d['id'])
        except Exception as e:
            logging.warning(f"[ExamRecommender] Department expansion error: {e}")

    target_dept_ids = list(set(target_dept_ids))

    # Fetch exam schedules in date window (past 7 days to next 45 days)
    try:
        q = client.table('exam_schedules').select(
            'id, subject_id, department_id, programme, semester, section, exam_date, start_time, end_time, exam_type, academic_term, is_reregistration, offered_in_semester, notes_flags, subjects(id, name, subject_code), departments(id, name, abbreviation)'
        ).eq('is_active', True)\
         .gte('exam_date', past_7_days_str)\
         .lte('exam_date', future_limit_str)\
         .order('exam_date', desc=False)

        if target_dept_ids:
            q = q.in_('department_id', target_dept_ids)

        schedules_res = q.execute()
        raw_schedules = schedules_res.data or []
    except Exception as e:
        logging.error(f"[ExamRecommender] Failed querying exam_schedules: {e}")
        raw_schedules = []

    matched_exams = []
    completed_exams_today = []
    today_exams = []
    upcoming_exams = []

    current_time_str = now_kolkata.strftime('%H:%M:%S')

    for s in raw_schedules:
        sem_str = str(s.get('semester') or '').strip().upper()
        offered_str = str(s.get('offered_in_semester') or '').strip().upper()
        sec_str = str(s.get('section') or '').strip().upper() if s.get('section') else None

        # Matches semester directly OR offered as re-registration in user's semester
        sem_match = (sem_str == user_sem or offered_str == user_sem or sem_str in user_sem or user_sem in sem_str)
        if not sem_match:
            continue

        if sec_str and user_sec and sec_str != 'ALL':
            if user_sec not in sec_str and sec_str not in user_sec:
                continue

        exam_date_obj = datetime.strptime(s['exam_date'], '%Y-%m-%d').date()
        days_left = (exam_date_obj - now_kolkata.date()).days
        s['days_until_exam'] = days_left

        sub_name = s.get('subjects', {}).get('name') if s.get('subjects') else 'Subject'
        sub_code = s.get('subjects', {}).get('subject_code') if s.get('subjects') else ''
        sid = s.get('subject_id')

        # Check completion state (today after end_time, or past 7 days)
        end_t = str(s.get('end_time') or '17:30:00')
        is_finished = False
        if days_left < 0:
            is_finished = True
        elif days_left == 0 and current_time_str >= end_t:
            is_finished = True

        if is_finished and days_left >= -7:
            days_ago = abs(days_left)
            s['is_completed_past_7_days'] = True
            s['status'] = 'COMPLETED'
            s['days_ago'] = days_ago
            s['countdown_label'] = 'Completed Today' if days_left == 0 else f"Completed {days_ago} day{'s' if days_ago > 1 else ''} ago"
            s['post_exam_prompt'] = {
                'subject_id': sid,
                'subject_name': sub_name,
                'subject_code': sub_code,
                'semester': s.get('semester'),
                'exam_type': s.get('exam_type', 'THEORY'),
                'academic_term': s.get('academic_term', 'Winter 2026'),
                'days_ago': days_ago,
                'upload_prefill_url': f"/upload?subject_id={sid}&subject_name={quote(sub_name)}&category=papers&title={quote(sub_name + ' — Winter 2026 ESE Question Paper')}&year=2026&semester={quote(s.get('semester') or '')}&exam_type={s.get('exam_type', 'THEORY')}"
            }
            completed_exams_today.append(s)
        elif days_left == 0:
            s['is_today'] = True
            s['status'] = 'TODAY'
            s['countdown_label'] = 'Exam is TODAY!'
            today_exams.append(s)
            upcoming_exams.append(s)
        elif days_left == 1:
            s['is_upcoming'] = True
            s['status'] = 'TOMORROW'
            s['countdown_label'] = 'Tomorrow'
            upcoming_exams.append(s)
        elif days_left > 1:
            s['is_upcoming'] = True
            s['status'] = 'UPCOMING'
            s['countdown_label'] = f"In {days_left} days"
            upcoming_exams.append(s)

        matched_exams.append(s)

    # Deduplicate upcoming exams by subject name/id so each distinct course appears only ONCE
    seen_subject_keys = set()
    deduped_upcoming = []
    for ex in upcoming_exams:
        sub_key = (ex.get('subjects', {}).get('name') or '').strip().lower() or ex.get('subject_id')
        if sub_key not in seen_subject_keys:
            seen_subject_keys.add(sub_key)
            deduped_upcoming.append(ex)
    upcoming_exams = deduped_upcoming

    seen_comp_keys = set()
    deduped_comp = []
    for ex in completed_exams_today:
        sub_key = (ex.get('subjects', {}).get('name') or '').strip().lower() or ex.get('subject_id')
        if sub_key not in seen_comp_keys:
            seen_comp_keys.add(sub_key)
            deduped_comp.append(ex)
    completed_exams_today = deduped_comp

    # Fetch relevant files for these subjects
    subject_ids = list({e['subject_id'] for e in matched_exams if e.get('subject_id')})
    docs_by_subject: Dict[str, List[dict]] = {}

    if subject_ids:
        try:
            docs_q = client.table('documents').select(
                'id, title, description, file_url, document_category, file_type, view_count, like_count, uploader_id, subject_id, exam_type, created_at, price, is_paid, profiles!documents_uploader_id_fkey(full_name)'
            ).in_('subject_id', subject_ids).eq('status', 'approved')

            docs_res = docs_q.execute()
            for doc in (docs_res.data or []):
                if user_id and doc.get('uploader_id') == user_id:
                    continue
                sid = doc.get('subject_id')
                docs_by_subject.setdefault(sid, []).append(doc)
        except Exception as e:
            logging.warning(f"[ExamRecommender] Docs query error: {e}")

    # Build ranked recommendations: PYQs first, then Notes (recent first)
    all_recommended_ids = set()
    flat_recommendations = []

    for exam in (upcoming_exams or matched_exams):
        sid = exam.get('subject_id')
        candidate_docs = list(docs_by_subject.get(sid, []))

        # Fallback keyword search if subject_id has few or no direct matches
        if len(candidate_docs) < 8:
            sub_name = (exam.get('subjects', {}).get('name') or '').strip()
            sub_code = (exam.get('subjects', {}).get('subject_code') or '').strip()
            search_terms = []
            if sub_name:
                clean = re.sub(r'(?i)\b(and|of|for|to|in|the)\b', ' ', sub_name)
                parts = [p.strip() for p in clean.split() if len(p.strip()) >= 3]
                if len(parts) >= 2:
                    search_terms.append(f"{parts[0]} {parts[1]}")
                elif len(parts) == 1:
                    search_terms.append(parts[0])
            if sub_code:
                search_terms.append(sub_code)

            for term in search_terms:
                try:
                    sq = client.table('documents').select(
                        'id, title, description, file_url, document_category, file_type, view_count, like_count, uploader_id, subject_id, exam_type, created_at, price, is_paid, profiles!documents_uploader_id_fkey(full_name)'
                    ).ilike('title', f"%{term}%").eq('status', 'approved').limit(15)
                    for d in (sq.execute().data or []):
                        if user_id and d.get('uploader_id') == user_id:
                            continue
                        if not any(cd['id'] == d['id'] for cd in candidate_docs):
                            candidate_docs.append(d)
                except Exception as err:
                    logging.warning(f"[ExamRecommender] Search fallback error: {err}")

        scored_docs = []
        exam_subj = exam.get('subjects') or {}
        sub_name = (exam_subj.get('name') or exam.get('subject_name') or 'Subject').strip()
        sub_code = (exam_subj.get('subject_code') or exam.get('subject_code') or '').strip()

        for doc in candidate_docs:
            d_copy = dict(doc)
            d_copy['match_score'] = calculate_file_exam_match_score(d_copy, exam)
            # Rule: Always show subject and subject code, never file title
            d_copy['subject'] = sub_name
            d_copy['subject_name'] = sub_name
            d_copy['subject_code'] = sub_code
            d_copy['subjects'] = {'name': sub_name, 'subject_code': sub_code}
            d_copy['for_exam'] = {
                'subject_name': sub_name,
                'subject_code': sub_code,
                'exam_type': exam.get('exam_type'),
                'exam_date': exam.get('exam_date'),
                'countdown': exam.get('countdown_label')
            }
            scored_docs.append(d_copy)

        scored_docs.sort(key=lambda x: x['match_score'], reverse=True)
        top_docs = scored_docs[:16]  # Allow pagination on client
        exam['top_files'] = top_docs

        for td in top_docs[:limit_per_exam]:
            did = td['id']
            if did not in all_recommended_ids:
                all_recommended_ids.add(did)
                flat_recommendations.append(td)

    flat_recommendations.sort(key=lambda x: x['match_score'], reverse=True)

    return {
        'source': 'timetable',
        'timezone': 'Asia/Kolkata',
        'as_of_date': today_str,
        'exams': upcoming_exams or matched_exams,
        'today_exams': today_exams,
        'completed_exams_today': completed_exams_today,
        'upcoming_exams': upcoming_exams,
        'recommended_files': flat_recommendations[:12]
    }


def dispatch_exam_countdown_reminders():
    """
    Periodic job: Scans upcoming exam schedules and notifies students at 14, 7, and 3 days before exams.
    Timezone: Asia/Kolkata.
    """
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'success': False, 'message': 'Client unavailable'}

    now_kolkata = get_current_kolkata_date()
    target_intervals = [14, 7, 3]
    notifications_sent = 0

    for days in target_intervals:
        target_date_str = (now_kolkata + timedelta(days=days)).strftime('%Y-%m-%d')
        try:
            s_res = client.table('exam_schedules').select(
                'id, subject_id, department_id, semester, exam_type, exam_date, subjects(name, subject_code)'
            ).eq('exam_date', target_date_str).eq('is_active', True).execute()

            schedules = s_res.data or []
            for s in schedules:
                dept_id = s.get('department_id')
                sem = s.get('semester')
                sub_name = s.get('subjects', {}).get('name') if s.get('subjects') else 'Upcoming Exam'
                sub_code = s.get('subjects', {}).get('subject_code') if s.get('subjects') else ''

                # Find students in this cohort
                stud_res = client.table('profiles').select('id')\
                    .eq('department_id', dept_id)\
                    .ilike('semester', f"%{sem}%").execute()

                for st in (stud_res.data or []):
                    uid = st.get('id')
                    if uid:
                        try:
                            from methods.supabase_helper import log_notification
                            log_notification(
                                user_id=uid,
                                title=f"Exam in {days} Days: {sub_code or sub_name}",
                                body=f"Your {s.get('exam_type', 'THEORY')} exam is scheduled for {s['exam_date']}. Check your recommended preparation materials.",
                                link="/#section-recommended"
                            )
                            notifications_sent += 1
                        except Exception:
                            pass
        except Exception as e:
            logging.warning(f"[ExamReminders] Error checking {days}-day interval: {e}")

    return {'success': True, 'notifications_sent': notifications_sent}

