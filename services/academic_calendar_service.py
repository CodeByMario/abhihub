"""
College-Wise Academic Schedule & Curriculum Syllabus Service.
Manages semester timelines (start, submission deadline, mid/end-sem exams, results)
and college-specific subjects, subject codes, and syllabi.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from methods.supabase_helper import init_supabase, init_supabase_admin

DEFAULT_GHRCE_ID = "87928d20-edb3-4185-94e3-b0678470e850"

# In-memory fallback defaults for GHRCE when table migration is pending
DEFAULT_GHRCE_SCHEDULE = {
    'college_id': DEFAULT_GHRCE_ID,
    'college_name': 'G H Raisoni College of Engineering (GHRCE Nagpur)',
    'academic_year': '2025-2026',
    'term': 'Winter 2026',
    'semester': 'All',
    'semester_start_date': '2025-07-15',
    'semester_end_date': '2025-12-15',
    'submission_start_date': '2025-10-25',
    'submission_deadline': '2025-11-10',
    'mid_sem_start_date': '2025-09-15',
    'mid_sem_end_date': '2025-09-22',
    'exam_start_date': '2025-11-18',
    'exam_end_date': '2025-12-12',
    'result_date': '2026-01-10',
    'notes': 'Autonomous Examination Cell - Winter 2026 Schedule'
}


def get_college_academic_schedule(college_id: str = DEFAULT_GHRCE_ID, term: str = 'Winter 2026') -> Dict[str, Any]:
    """
    Retrieves the semester schedule (start date, submission deadline, exam dates, results).
    """
    client = init_supabase_admin() or init_supabase()
    target_college_id = college_id or DEFAULT_GHRCE_ID

    if client:
        try:
            res = client.table('college_academic_schedules')\
                .select('*')\
                .eq('college_id', target_college_id)\
                .eq('term', term)\
                .limit(1)\
                .execute()

            if res.data and len(res.data) > 0:
                schedule = res.data[0]
                return {'success': True, 'schedule': schedule}
        except Exception as e:
            logging.debug(f"[AcademicSchedule] Table query note (falling back to baseline): {e}")

    # Fallback to default GHRCE schedule or synthesized calendar
    schedule = dict(DEFAULT_GHRCE_SCHEDULE)
    schedule['college_id'] = target_college_id
    if target_college_id != DEFAULT_GHRCE_ID and client:
        try:
            col_res = client.table('colleges').select('name').eq('id', target_college_id).limit(1).execute()
            if col_res.data:
                schedule['college_name'] = col_res.data[0].get('name', 'College')
        except Exception:
            pass

    return {'success': True, 'schedule': schedule, 'is_fallback': True}


def save_college_academic_schedule(college_id: str, data: dict, user: Optional[dict] = None) -> Dict[str, Any]:
    """
    Creates or updates the college-wise academic schedule.
    """
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'success': False, 'message': 'Database client unavailable'}

    record = {
        'college_id': college_id or DEFAULT_GHRCE_ID,
        'academic_year': data.get('academic_year') or '2025-2026',
        'term': data.get('term') or 'Winter 2026',
        'semester': data.get('semester') or 'All',
        'semester_start_date': data.get('semester_start_date') or None,
        'semester_end_date': data.get('semester_end_date') or None,
        'submission_start_date': data.get('submission_start_date') or None,
        'submission_deadline': data.get('submission_deadline') or None,
        'mid_sem_start_date': data.get('mid_sem_start_date') or None,
        'mid_sem_end_date': data.get('mid_sem_end_date') or None,
        'exam_start_date': data.get('exam_start_date') or None,
        'exam_end_date': data.get('exam_end_date') or None,
        'result_date': data.get('result_date') or None,
        'notes': data.get('notes') or None,
        'updated_at': datetime.now(timezone.utc).isoformat()
    }

    try:
        res = client.table('college_academic_schedules').upsert(record).execute()
        return {'success': True, 'data': res.data}
    except Exception as e:
        logging.error(f"[AcademicSchedule] Save error: {e}")
        return {'success': False, 'message': str(e)}


def get_college_subjects(college_id: str = DEFAULT_GHRCE_ID, department_id: Optional[str] = None, semester: Optional[str] = None, search: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches curriculum subjects, codes, credits, and syllabus details for a college branch & sem.
    """
    client = init_supabase_admin() or init_supabase()
    target_college_id = college_id or DEFAULT_GHRCE_ID

    if not client:
        return {'success': False, 'subjects': [], 'total': 0}

    # 1. Try querying college_subjects table
    try:
        q = client.table('college_subjects')\
            .select('id, college_id, department_id, semester, subject_name, subject_code, syllabus_text, syllabus_pdf_url, credits, regulation')\
            .eq('college_id', target_college_id)

        if department_id:
            q = q.eq('department_id', department_id)
        if semester:
            q = q.eq('semester', semester)
        if search:
            q = q.or_(f"subject_name.ilike.%{search}%,subject_code.ilike.%{search}%")

        res = q.order('subject_code').execute()
        if res.data:
            return {'success': True, 'subjects': res.data, 'total': len(res.data)}
    except Exception as e:
        logging.debug(f"[AcademicSchedule] college_subjects lookup note: {e}")

    # 2. Fallback to existing abhihub.subjects joined with departments
    try:
        sq = client.table('subjects').select('id, name, subject_code, department_id, semester')
        if department_id:
            sq = sq.eq('department_id', department_id)
        if semester:
            sq = sq.eq('semester', semester)
        if search:
            sq = sq.or_(f"name.ilike.%{search}%,subject_code.ilike.%{search}%")

        sres = sq.order('subject_code').limit(100).execute()
        mapped = []
        for s in (sres.data or []):
            mapped.append({
                'id': s.get('id'),
                'college_id': target_college_id,
                'department_id': s.get('department_id'),
                'semester': s.get('semester') or 'N/A',
                'subject_name': s.get('name'),
                'subject_code': s.get('subject_code'),
                'syllabus_text': f"Curriculum and syllabus units for {s.get('name')} ({s.get('subject_code')}).",
                'syllabus_pdf_url': None,
                'credits': 3,
                'regulation': 'Autonomous'
            })
        return {'success': True, 'subjects': mapped, 'total': len(mapped), 'is_fallback': True}
    except Exception as err:
        logging.error(f"[AcademicSchedule] Fallback subjects query error: {err}")
        return {'success': False, 'subjects': [], 'total': 0, 'message': str(err)}


def save_college_subject(college_id: str, data: dict) -> Dict[str, Any]:
    """
    Upserts a college curriculum subject with syllabus content and course code.
    """
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'success': False, 'message': 'Database client unavailable'}

    record = {
        'college_id': college_id or DEFAULT_GHRCE_ID,
        'department_id': data.get('department_id') or None,
        'semester': str(data.get('semester', '1')).strip(),
        'subject_name': data.get('subject_name', '').strip(),
        'subject_code': data.get('subject_code', '').strip().upper(),
        'syllabus_text': data.get('syllabus_text') or None,
        'syllabus_pdf_url': data.get('syllabus_pdf_url') or None,
        'credits': float(data.get('credits', 3) or 3),
        'academic_year': data.get('academic_year') or '2025-2026',
        'regulation': data.get('regulation') or 'Autonomous',
        'updated_at': datetime.now(timezone.utc).isoformat()
    }

    try:
        res = client.table('college_subjects').upsert(record).execute()
        return {'success': True, 'data': res.data}
    except Exception as e:
        # If college_subjects table is not migrated yet, also ensure base subjects table has it
        try:
            client.table('subjects').upsert({
                'name': record['subject_name'],
                'subject_code': record['subject_code'],
                'department_id': record['department_id'],
                'semester': record['semester']
            }).execute()
            return {'success': True, 'message': 'Saved to canonical subjects catalog', 'is_fallback': True}
        except Exception as inner_err:
            logging.error(f"[AcademicSchedule] Save subject fallback error: {inner_err}")
            return {'success': False, 'message': str(e)}
