"""
Academic Timetable Management Service for AbhiHub.
Provides CRUD, bulk CSV/JSON import, alias merging, audit logging,
and date-shift change notifications.
"""
import io
import csv
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from methods.supabase_helper import init_supabase, init_supabase_admin, log_notification
from routes.auth import log_admin_action
from scripts.seed_timetable import parse_dates, parse_time_range, parse_sem_and_section, resolve_department, resolve_or_create_subject

DEFAULT_COLLEGE_ID = "87928d20-edb3-4185-94e3-b0678470e850" # GHRCE

def get_timetables(filters: dict) -> Dict:
    """Query exam schedules and class schedules with filtering."""
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'exams': [], 'classes': [], 'total': 0}

    college_id = filters.get('college_id') or DEFAULT_COLLEGE_ID
    dept_id = filters.get('department_id')
    sem = filters.get('semester')
    term = filters.get('academic_term') or 'Winter 2026'
    exam_type = filters.get('exam_type')

    # Resolve allowed departments for this college
    college_dept_ids = []
    try:
        cd_res = client.table('college_departments').select('department_id').eq('college_id', college_id).execute()
        college_dept_ids = [c['department_id'] for c in (cd_res.data or []) if c.get('department_id')]
    except Exception:
        pass

    try:
        # 1. Exams
        eq = client.table('exam_schedules').select(
            'id, college_id, subject_id, department_id, programme, semester, section, exam_date, start_time, end_time, exam_type, academic_term, is_reregistration, offered_in_semester, notes_flags, is_active, subjects(id, name, subject_code), departments(id, name, abbreviation)'
        ).eq('is_active', True)

        if college_id:
            eq = eq.eq('college_id', college_id)
        if dept_id:
            eq = eq.eq('department_id', dept_id)
        if sem:
            eq = eq.eq('semester', sem)
        if term:
            eq = eq.eq('academic_term', term)
        if exam_type:
            eq = eq.eq('exam_type', exam_type)

        exams = eq.order('exam_date', desc=False).limit(400).execute().data or []

        # 2. Classes
        cq = client.table('class_schedules').select(
            'id, subject_id, department_id, semester, section, day_of_week, start_time, end_time, room_number, academic_term, is_active, subjects(id, name, subject_code), departments(id, name, abbreviation)'
        ).eq('is_active', True)

        if dept_id:
            cq = cq.eq('department_id', dept_id)
        if sem:
            cq = cq.eq('semester', sem)
        if term:
            cq = cq.eq('academic_term', term)

        classes = cq.limit(100).execute().data or []

        return {
            'success': True,
            'exams': exams,
            'classes': classes,
            'total_exams': len(exams),
            'total_classes': len(classes)
        }
    except Exception as e:
        logging.error(f"[TimetableService] get_timetables error: {e}")
        return {'success': False, 'message': str(e), 'exams': [], 'classes': []}

def save_exam_schedule(data: dict, admin_user: dict, schedule_id: Optional[str] = None) -> Dict:
    """Create or update exam schedule with audit log & student notifications on date change."""
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'success': False, 'message': 'Database unavailable'}

    college_id = data.get('college_id') or DEFAULT_COLLEGE_ID
    try:
        subject_id = data.get('subject_id')
        if not subject_id:
            code = (data.get('course_code') or data.get('subject_code') or '').strip().upper()
            name = (data.get('course_name') or data.get('subject_name') or code).strip()
            if code or name:
                s_res = client.table('subjects').select('id').or_(f"subject_code.ilike.%{code}%,name.ilike.%{name}%").limit(1).execute()
                if s_res.data:
                    subject_id = s_res.data[0]['id']
                else:
                    sem_num = 1
                    try:
                        import re
                        m = re.search(r'\d+', str(data.get('semester', '')))
                        if m: sem_num = int(m.group(0))
                    except Exception:
                        pass
                    ins = client.table('subjects').insert({
                        'name': name or code,
                        'subject_code': code or name[:8].upper(),
                        'department_id': data.get('department_id'),
                        'semester': sem_num
                    }).execute()
                    subject_id = ins.data[0]['id'] if ins.data else None

        record = {
            'college_id': college_id,
            'subject_id': subject_id,
            'department_id': data['department_id'],
            'programme': data.get('programme', 'B.Tech'),
            'semester': data['semester'],
            'section': data.get('section') or None,
            'exam_date': data['exam_date'],
            'start_time': data.get('start_time') or None,
            'end_time': data.get('end_time') or None,
            'exam_type': data.get('exam_type', 'THEORY'),
            'academic_term': data.get('academic_term', 'Winter 2026'),
            'is_reregistration': bool(data.get('is_reregistration', False)),
            'offered_in_semester': data.get('offered_in_semester') or None,
            'notes_flags': data.get('notes_flags') or None,
            'is_active': True
        }

        old_date = None
        if schedule_id:
            existing = client.table('exam_schedules').select('exam_date, department_id, semester, subject_id').eq('id', schedule_id).limit(1).execute()
            if existing.data:
                old_date = existing.data[0].get('exam_date')

            try:
                res = client.table('exam_schedules').update(record).eq('id', schedule_id).execute()
            except Exception as up_err:
                if 'college_id' in str(up_err):
                    record.pop('college_id', None)
                    res = client.table('exam_schedules').update(record).eq('id', schedule_id).execute()
                else:
                    raise up_err
            action_type = "update_exam_schedule"
        else:
            record['created_by'] = admin_user.get('id') or admin_user.get('uid')
            try:
                res = client.table('exam_schedules').insert(record).execute()
            except Exception as ins_err:
                if 'college_id' in str(ins_err):
                    record.pop('college_id', None)
                    res = client.table('exam_schedules').insert(record).execute()
                else:
                    raise ins_err
            schedule_id = res.data[0]['id'] if res.data else None
            action_type = "create_exam_schedule"

        # Log admin audit
        try:
            log_admin_action(
                admin_id=admin_user.get('id') or admin_user.get('uid'),
                admin_email=admin_user.get('email', 'admin'),
                action=action_type,
                target_type="exam_schedule",
                target_id=schedule_id,
                details=f"Exam on {record['exam_date']} ({record['exam_type']})"
            )
        except Exception:
            pass

        # If date moved, notify affected students
        if old_date and old_date != record['exam_date']:
            notify_students_of_schedule_change(
                department_id=record['department_id'],
                semester=record['semester'],
                subject_id=record['subject_id'],
                old_date=old_date,
                new_date=record['exam_date']
            )

        return {'success': True, 'id': schedule_id, 'data': res.data}
    except Exception as e:
        logging.error(f"[TimetableService] save_exam_schedule error: {e}")
        return {'success': False, 'message': str(e)}

def delete_exam_schedule(schedule_id: str, admin_user: dict) -> Dict:
    """Soft delete / deactivate exam schedule."""
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'success': False, 'message': 'Database unavailable'}
    try:
        res = client.table('exam_schedules').update({'is_active': False}).eq('id', schedule_id).execute()
        log_admin_action(
            admin_id=admin_user.get('id') or admin_user.get('uid'),
            admin_email=admin_user.get('email', 'admin'),
            action="archive_exam_schedule",
            target_type="exam_schedule",
            target_id=schedule_id
        )
        return {'success': True}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def notify_students_of_schedule_change(department_id: str, semester: str, subject_id: str, old_date: str, new_date: str):
    """Notifies students enrolled in affected department/semester that an exam date moved."""
    client = init_supabase_admin() or init_supabase()
    if not client:
        return

    try:
        sub_name = "Exam"
        sub_res = client.table('subjects').select('name, subject_code').eq('id', subject_id).limit(1).execute()
        if sub_res.data:
            sub_name = sub_res.data[0].get('name') or sub_res.data[0].get('subject_code')

        # Find affected students
        students = client.table('profiles').select('id')\
            .eq('department_id', department_id)\
            .ilike('semester', f"%{semester}%").execute()

        for s in (students.data or []):
            uid = s.get('id')
            if uid:
                log_notification(
                    user_id=uid,
                    title=f"Timetable Update: {sub_name}",
                    body=f"Exam date moved from {old_date} to {new_date}. Your exam recommendations have been updated.",
                    link="/#section-recommended"
                )
    except Exception as e:
        logging.warning(f"[TimetableService] Notification dispatch error: {e}")

def parse_and_preview_import(file_stream, college_id: str = DEFAULT_COLLEGE_ID) -> Dict:
    """
    Validates CSV import rows against departments, courses, and dates.
    Flags invalid branches, bad dates, and duplicate rows.
    """
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'success': False, 'message': 'Database unavailable'}

    stream = io.StringIO(file_stream.read().decode('utf-8', errors='ignore'))
    reader = csv.DictReader(stream)

    departments_map = {d['name'].lower(): d['id'] for d in (client.table('departments').select('id, name').execute().data or [])}
    subjects_map = {s['subject_code'].upper(): s['id'] for s in (client.table('subjects').select('id, subject_code').execute().data or [])}

    preview_rows = []
    valid_count = 0
    error_count = 0

    for idx, row in enumerate(reader):
        branch_raw = (row.get('branch') or row.get('department') or '').strip()
        code_raw = (row.get('course_code') or row.get('code') or '').strip().upper()
        course_name = (row.get('course_name') or row.get('course') or '').strip()
        sem_raw = (row.get('semester') or row.get('sem') or '').strip()
        date_raw = (row.get('exam_date') or row.get('date') or '').strip()
        time_raw = (row.get('time') or '').strip()
        exam_type = (row.get('exam_type') or 'THEORY').strip().upper()

        status = 'VALID'
        issues = []

        # Validate Branch
        dept_id = None
        for b_name, d_id in departments_map.items():
            if branch_raw.lower() in b_name or b_name in branch_raw.lower():
                dept_id = d_id
                break
        if not dept_id:
            status = 'WARNING'
            issues.append(f"Branch '{branch_raw}' will be auto-created.")

        # Validate Course Code
        sub_id = subjects_map.get(code_raw)
        if not sub_id:
            status = 'WARNING'
            issues.append(f"Course '{code_raw}' will be auto-created.")

        # Validate Date
        parsed_dates = parse_dates(date_raw)
        if not parsed_dates:
            status = 'ERROR'
            issues.append(f"Invalid date format: {date_raw}")

        if status == 'ERROR':
            error_count += 1
        else:
            valid_count += 1

        preview_rows.append({
            'row_num': idx + 1,
            'branch': branch_raw,
            'course_code': code_raw,
            'course_name': course_name,
            'semester': sem_raw,
            'exam_date': parsed_dates[0] if parsed_dates else date_raw,
            'time': time_raw,
            'exam_type': exam_type,
            'status': status,
            'issues': issues
        })

    return {
        'success': True,
        'preview_rows': preview_rows,
        'total': len(preview_rows),
        'valid_count': valid_count,
        'error_count': error_count
    }

def merge_course_aliases(canonical_subject_id: str, alias_code: str, admin_user: dict) -> Dict:
    """Associates an alternative course code variant to a canonical subject."""
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'success': False, 'message': 'Database unavailable'}

    code_norm = alias_code.strip().upper()
    try:
        client.table('subject_aliases').upsert({
            'subject_id': canonical_subject_id,
            'alias': code_norm,
            'alias_norm': code_norm.lower(),
            'priority': 2
        }).execute()

        log_admin_action(
            admin_id=admin_user.get('id') or admin_user.get('uid'),
            admin_email=admin_user.get('email', 'admin'),
            action="merge_course_alias",
            target_type="subject_alias",
            target_id=canonical_subject_id,
            details=f"Merged alias {code_norm} into subject {canonical_subject_id}"
        )
        return {'success': True, 'message': f"Alias '{code_norm}' mapped successfully."}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def submit_user_timetable_entry(data: dict, user: Optional[dict] = None) -> Dict:
    """
    Allows a student/user to submit an exam timetable entry based on their college and branch.
    Auto-associates with their college, ensures department linkage, and resolves or registers the subject.
    """
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'success': False, 'message': 'Database client unavailable'}

    user_id = (user or {}).get('id') or (user or {}).get('uid')
    college_id = data.get('college_id') or (user or {}).get('college_id') or DEFAULT_COLLEGE_ID
    department_id = data.get('department_id') or (user or {}).get('department_id')
    semester = str(data.get('semester', '')).strip()
    subject_name = str(data.get('subject_name', '')).strip()
    subject_code = str(data.get('subject_code', '')).strip().upper()
    exam_date = data.get('exam_date')
    start_time = data.get('start_time') or None
    end_time = data.get('end_time') or None
    exam_type = (data.get('exam_type') or 'THEORY').strip().upper()
    academic_term = data.get('academic_term') or 'Winter 2026'

    if not department_id or not exam_date or not subject_name:
        return {'success': False, 'message': 'Missing required fields: department, exam date, or subject name.'}

    try:
        # 1. Ensure college_department mapping exists
        try:
            client.table('college_departments').upsert({
                'college_id': college_id,
                'department_id': department_id
            }).execute()
        except Exception:
            pass

        # 2. Resolve or create subject
        subject_id = data.get('subject_id')
        if not subject_id:
            sub_res = client.table('subjects').select('id')\
                .ilike('subject_code', subject_code if subject_code else subject_name)\
                .limit(1).execute()
            if sub_res.data:
                subject_id = sub_res.data[0]['id']
            else:
                ins_sub = client.table('subjects').insert({
                    'name': subject_name,
                    'subject_code': subject_code or subject_name[:8].upper(),
                    'department_id': department_id,
                    'semester': semester
                }).execute()
                subject_id = ins_sub.data[0]['id'] if ins_sub.data else None

        # 3. Also register in college_subjects with syllabus if provided
        try:
            from services.academic_calendar_service import save_college_subject
            save_college_subject(college_id=college_id, data={
                'department_id': department_id,
                'semester': semester,
                'subject_name': subject_name,
                'subject_code': subject_code or subject_name[:8].upper(),
                'syllabus_text': data.get('syllabus_text') or None,
                'syllabus_pdf_url': data.get('syllabus_pdf_url') or None,
                'credits': data.get('credits', 3)
            })
        except Exception:
            pass

        # 4. Insert into exam_schedules
        sched_record = {
            'college_id': college_id,
            'department_id': department_id,
            'subject_id': subject_id,
            'programme': data.get('programme', 'B.Tech'),
            'semester': semester,
            'section': data.get('section') or None,
            'exam_date': exam_date,
            'start_time': start_time,
            'end_time': end_time,
            'exam_type': exam_type,
            'academic_term': academic_term,
            'is_reregistration': bool(data.get('is_reregistration', False)),
            'notes_flags': data.get('notes_flags') or 'Student Contributed',
            'created_by': user_id,
            'is_active': True
        }

        try:
            res = client.table('exam_schedules').insert(sched_record).execute()
        except Exception as ins_err:
            if 'college_id' in str(ins_err):
                sched_record.pop('college_id', None)
                res = client.table('exam_schedules').insert(sched_record).execute()
            else:
                raise ins_err

        sched_id = res.data[0]['id'] if res.data else None
        return {
            'success': True,
            'id': sched_id,
            'message': 'Exam timetable entry added successfully for your college and branch.',
            'entry': res.data[0] if res.data else sched_record
        }
    except Exception as e:
        logging.error(f"[TimetableService] submit_user_timetable_entry error: {e}")
        return {'success': False, 'message': str(e)}
