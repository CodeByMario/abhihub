"""
Notes in Demand & Demand Forecast Service for AbhiHub.
Computes course demand based on upcoming exam dates, student cohort size,
open request upvotes, and existing document supply gaps.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import zoneinfo

from methods.supabase_helper import init_supabase, init_supabase_admin

KOLKATA_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")

def compute_course_demand_forecast(college_id: Optional[str] = None) -> List[Dict]:
    """
    Computes upcoming demand across all courses in the next 30 days.
    Formula:
    Demand Score = (Students * 0.5) + ProximityBonus + (OpenRequestUpvotes * 2.0) - (ExistingFiles * 3.0)
    Demand Level: High (>= 40), Medium (20-39), Low (< 20)
    """
    client = init_supabase_admin() or init_supabase()
    if not client:
        return []

    now_kolkata = datetime.now(KOLKATA_TZ)
    today_str = now_kolkata.strftime('%Y-%m-%d')
    limit_30d_str = (now_kolkata + timedelta(days=30)).strftime('%Y-%m-%d')

    try:
        # 1. Fetch upcoming exam schedules in next 30 days
        sched_q = client.table('exam_schedules').select(
            'id, subject_id, department_id, semester, section, exam_date, exam_type, subjects(id, name, subject_code), departments(id, name, abbreviation)'
        ).eq('is_active', True)\
         .gte('exam_date', today_str)\
         .lte('exam_date', limit_30d_str)\
         .order('exam_date', desc=False)

        sched_res = sched_q.execute()
        schedules = sched_res.data or []
    except Exception as e:
        logging.error(f"[DemandService] Error querying exam_schedules: {e}")
        return []

    if not schedules:
        return []

    # 2. Get registered students count per department and semester
    student_counts: Dict[str, int] = {}
    try:
        prof_res = client.table('profiles').select('id, department_id, semester').execute()
        for p in (prof_res.data or []):
            dept = p.get('department_id')
            sem = (p.get('semester') or '').strip().upper()
            if dept and sem:
                key = f"{dept}:{sem}"
                student_counts[key] = student_counts.get(key, 0) + 1
    except Exception as e:
        logging.warning(f"[DemandService] Could not aggregate student counts: {e}")

    # 3. Get open requests and upvotes per subject
    open_requests_by_sub: Dict[str, Dict] = {}
    try:
        req_res = client.table('material_requests').select(
            'id, subject_id, upvotes_count, status'
        ).eq('status', 'OPEN').execute()
        for r in (req_res.data or []):
            sid = r.get('subject_id')
            if sid:
                stats = open_requests_by_sub.setdefault(sid, {'count': 0, 'upvotes': 0})
                stats['count'] += 1
                stats['upvotes'] += int(r.get('upvotes_count') or 0)
    except Exception as e:
        logging.warning(f"[DemandService] Error querying material_requests: {e}")

    # 4. Get existing approved file count per subject
    subject_ids = list({s['subject_id'] for s in schedules if s.get('subject_id')})
    file_counts: Dict[str, int] = {}
    if subject_ids:
        try:
            docs_res = client.table('documents').select('subject_id')\
                .in_('subject_id', subject_ids)\
                .eq('status', 'approved').execute()
            for d in (docs_res.data or []):
                sid = d.get('subject_id')
                if sid:
                    file_counts[sid] = file_counts.get(sid, 0) + 1
        except Exception as e:
            logging.warning(f"[DemandService] Error querying documents count: {e}")

    # 5. Compute demand items
    forecast_map = {}
    for s in schedules:
        sub_id = s.get('subject_id')
        if not sub_id:
            continue

        exam_date_obj = datetime.strptime(s['exam_date'], '%Y-%m-%d').date()
        days_left = max(0, (exam_date_obj - now_kolkata.date()).days)

        dept_id = s.get('department_id')
        sem_str = (s.get('semester') or '').strip().upper()
        cohort_key = f"{dept_id}:{sem_str}"
        est_students = max(student_counts.get(cohort_key, 0), 25) # baseline active student estimate

        req_stats = open_requests_by_sub.get(sub_id, {'count': 0, 'upvotes': 0})
        existing_supply = file_counts.get(sub_id, 0)

        # Proximity bonus: closer exam date receives higher urgency weight
        proximity_bonus = (30 - days_left) * 1.5

        demand_score = (est_students * 0.4) + proximity_bonus + (req_stats['upvotes'] * 2.5) - (existing_supply * 4.0)
        demand_score = round(max(0.0, demand_score), 1)

        if demand_score >= 40.0:
            level = "High"
        elif demand_score >= 20.0:
            level = "Medium"
        else:
            level = "Low"

        course_name = s.get('subjects', {}).get('name') if s.get('subjects') else 'Subject'
        course_code = s.get('subjects', {}).get('subject_code') if s.get('subjects') else ''
        branch_name = s.get('departments', {}).get('abbreviation') or s.get('departments', {}).get('name') if s.get('departments') else 'Branch'

        # Build summary narrative
        reasoning = (
            f"Exam in {days_left} days, ~{est_students} students preparing, "
            f"only {existing_supply} verified file(s) available, {req_stats['upvotes']} student upvote(s)."
        )

        key = f"{sub_id}:{s['exam_date']}"
        if key not in forecast_map or forecast_map[key]['demand_score'] < demand_score:
            forecast_map[key] = {
                'subject_id': sub_id,
                'course_name': course_name,
                'course_code': course_code,
                'branch': branch_name,
                'semester': s.get('semester'),
                'exam_date': s['exam_date'],
                'exam_type': s.get('exam_type', 'THEORY'),
                'days_until_exam': days_left,
                'student_count': est_students,
                'existing_files': existing_supply,
                'open_requests': req_stats['count'],
                'total_upvotes': req_stats['upvotes'],
                'demand_score': demand_score,
                'demand_level': level,
                'reasoning': reasoning,
                'high_earning_potential': (level == "High" and existing_supply <= 2)
            }

    forecast_list = list(forecast_map.values())
    forecast_list.sort(key=lambda x: (x['demand_score'], -x['days_until_exam']), reverse=True)
    return forecast_list

def create_material_request(requester_id: str, subject_id: str, title: str, details: str = "", exam_type: str = "THEORY", college_id: str = None) -> Dict:
    """Create a new student note/material request."""
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'success': False, 'message': 'Database unavailable'}

    try:
        # Fetch subject name
        s_res = client.table('subjects').select('name, department_id').eq('id', subject_id).limit(1).execute()
        subject_name = s_res.data[0]['name'] if s_res.data else title
        dept_id = s_res.data[0].get('department_id') if s_res.data else None

        ins_payload = {
            'requester_id': requester_id,
            'subject_id': subject_id,
            'department_id': dept_id,
            'college_id': college_id,
            'subject': subject_name,
            'title': title,
            'details': details,
            'exam_type': exam_type,
            'status': 'OPEN',
            'upvotes_count': 1
        }
        res = client.table('material_requests').insert(ins_payload).execute()
        if not res.data:
            return {'success': False, 'message': 'Failed creating request'}

        req_id = res.data[0]['id']
        # Requester automatically upvotes their own request
        try:
            client.table('material_request_votes').insert({
                'request_id': req_id,
                'user_id': requester_id
            }).execute()
        except Exception:
            pass

        return {'success': True, 'request_id': req_id, 'message': 'Request posted successfully'}
    except Exception as e:
        logging.error(f"[DemandService] create_material_request error: {e}")
        return {'success': False, 'message': str(e)}

def toggle_request_vote(request_id: str, user_id: str) -> Dict:
    """Toggles upvote for a material request (one vote per user)."""
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'success': False, 'message': 'Database unavailable'}

    try:
        # Check existing vote
        v_res = client.table('material_request_votes').select('id')\
            .eq('request_id', request_id)\
            .eq('user_id', user_id).execute()

        req_res = client.table('material_requests').select('upvotes_count').eq('id', request_id).limit(1).execute()
        if not req_res.data:
            return {'success': False, 'message': 'Request not found'}
        current_upvotes = int(req_res.data[0].get('upvotes_count') or 0)

        if v_res.data:
            # Remove upvote
            client.table('material_request_votes').delete().eq('id', v_res.data[0]['id']).execute()
            new_count = max(0, current_upvotes - 1)
            client.table('material_requests').update({'upvotes_count': new_count}).eq('id', request_id).execute()
            return {'success': True, 'action': 'unvoted', 'upvotes_count': new_count}
        else:
            # Add upvote
            client.table('material_request_votes').insert({'request_id': request_id, 'user_id': user_id}).execute()
            new_count = current_upvotes + 1
            client.table('material_requests').update({'upvotes_count': new_count}).eq('id', request_id).execute()
            return {'success': True, 'action': 'voted', 'upvotes_count': new_count}
    except Exception as e:
        logging.error(f"[DemandService] toggle_request_vote error: {e}")
        return {'success': False, 'message': str(e)}

def fulfill_request_with_document(request_id: str, document_id: str, responder_id: str) -> Dict:
    """Links an uploaded file to a material request and marks it FULFILLED."""
    client = init_supabase_admin() or init_supabase()
    if not client:
        return {'success': False, 'message': 'Database unavailable'}

    try:
        res = client.table('material_requests').update({
            'status': 'FULFILLED',
            'fulfilled_by_document_id': document_id,
            'responder_id': responder_id,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', request_id).execute()

        # Notify requester
        if res.data:
            requester_id = res.data[0].get('requester_id')
            subject_name = res.data[0].get('subject', 'Course')
            if requester_id:
                try:
                    from methods.supabase_helper import log_notification
                    log_notification(
                        user_id=requester_id,
                        title="Material Request Fulfilled!",
                        body=f"Study material has been uploaded for your request on {subject_name}.",
                        link=f"/document/{document_id}"
                    )
                except Exception:
                    pass

        return {'success': True, 'message': 'Request marked as fulfilled'}
    except Exception as e:
        logging.error(f"[DemandService] fulfill_request_with_document error: {e}")
        return {'success': False, 'message': str(e)}
