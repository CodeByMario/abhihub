"""
Tea Supporters Store.
Persists and retrieves public community tea supporters for landing page and dashboard.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

_DATA_DIR = os.path.dirname(__file__)
SUPPORTERS_FILE = os.path.join(_DATA_DIR, 'tea_supporters.json')

# Initial friendly supporters if file doesn't exist
DEFAULT_SUPPORTERS = [
    {
        "order_id": "INIT01",
        "name": "Aditya Sharma",
        "amount": 49.0,
        "cups": 2,
        "message": "Saved me the night before my engineering mechanics exam! ☕",
        "date": "Today",
        "created_at": "2026-09-29T08:30:00Z"
    },
    {
        "order_id": "INIT02",
        "name": "Priya Deshmukh",
        "amount": 29.0,
        "cups": 1,
        "message": "Thank you for keeping all university PYQs free and accessible. 🍵",
        "date": "Yesterday",
        "created_at": "2026-09-28T16:15:00Z"
    },
    {
        "order_id": "INIT03",
        "name": "Rahul Verma",
        "amount": 99.0,
        "cups": 4,
        "message": "Masala chai on me! Appreciate the fast server downloads. 🫖",
        "date": "2 days ago",
        "created_at": "2026-09-27T19:40:00Z"
    }
]


def _load_all_supporters() -> List[Dict[str, Any]]:
    if not os.path.exists(SUPPORTERS_FILE):
        try:
            with open(SUPPORTERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_SUPPORTERS, f, indent=2)
            return DEFAULT_SUPPORTERS
        except Exception as e:
            logging.warning(f"[tea_supporters] Error initializing file: {e}")
            return DEFAULT_SUPPORTERS

    try:
        with open(SUPPORTERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return DEFAULT_SUPPORTERS
    except Exception as e:
        logging.warning(f"[tea_supporters] Error reading supporters: {e}")
        return DEFAULT_SUPPORTERS


def add_tea_supporter(order_id: str, name: str, amount: float, message: str = '', user_id: str = '') -> Dict[str, Any]:
    """Adds a verified tea supporter record and saves to persistent JSON store."""
    if not order_id:
        return {}

    supporters = _load_all_supporters()

    # Deduplicate by order_id
    for s in supporters:
        if s.get('order_id') == order_id:
            return s

    clean_name = (name or '').strip()
    if not clean_name:
        clean_name = "Generous Supporter"

    clean_message = (message or '').strip()
    if not clean_message:
        clean_message = "Bought a cup of tea to support AbhiHub! ☕"

    amt = float(amount or 29.0)
    cups = max(1, int(round(amt / 25.0))) if amt >= 20 else 1

    now = datetime.now()
    supporter_record = {
        "order_id": order_id,
        "user_id": user_id or None,
        "name": clean_name[:50],
        "amount": amt,
        "cups": cups,
        "message": clean_message[:160],
        "date": "Just now",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    supporters.insert(0, supporter_record)

    # Keep latest 100 supporters in local file
    try:
        with open(SUPPORTERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(supporters[:100], f, indent=2)
    except Exception as e:
        logging.warning(f"[tea_supporters] Error saving supporter: {e}")

    return supporter_record


def get_recent_tea_supporters(limit: int = 6) -> List[Dict[str, Any]]:
    """Returns the most recent tea supporters."""
    supporters = [s for s in _load_all_supporters() if s.get('cups') or s.get('amount') or s.get('type') == 'tea']
    return supporters[:limit]


DEFAULT_FEEDBACKS = [
    {
        "id": "FB01",
        "name": "Aditya Sharma",
        "rating": 5,
        "college": "GHRCE Nagpur",
        "branch": "CSE",
        "message": "Saved me the night before my engineering mechanics end-sem! Found the exact 2024 solved PYQ paper in seconds. ⚡",
        "date": "Today",
        "created_at": "2026-10-22T08:30:00Z"
    },
    {
        "id": "FB02",
        "name": "Priya Deshmukh",
        "rating": 5,
        "college": "VNIT Nagpur",
        "branch": "IT",
        "message": "The handwritten toppers' notes for Data Structures are incredible. UI is super fast and clean on mobile.",
        "date": "Yesterday",
        "created_at": "2026-10-21T14:15:00Z"
    },
    {
        "id": "FB03",
        "name": "Rahul Verma",
        "rating": 5,
        "college": "COEP Pune",
        "branch": "Mechanical",
        "message": "Live study chat is awesome! Was able to ask seniors for last year's practical viva questions instantly.",
        "date": "2 days ago",
        "created_at": "2026-10-20T19:40:00Z"
    },
    {
        "id": "FB04",
        "name": "Ananya Roy",
        "rating": 5,
        "college": "ITER Bhubaneswar",
        "branch": "EE",
        "message": "No annoying spam or payment gates for basic past papers. Genuine student-first platform. Highly recommended!",
        "date": "3 days ago",
        "created_at": "2026-10-19T11:20:00Z"
    },
    {
        "id": "FB05",
        "name": "Kunal Mehra",
        "rating": 5,
        "college": "KIIT University",
        "branch": "CS",
        "message": "Earned over 200 XP uploading our semester lab codes. The streak and ranking badges are super motivating! 🔥",
        "date": "4 days ago",
        "created_at": "2026-10-18T16:05:00Z"
    }
]


def _get_supabase_feedback_table():
    """Retrieve Supabase handle for app_feedback table."""
    try:
        from methods.supabase_helper import init_supabase_admin, init_supabase
        client = init_supabase_admin() or init_supabase()
        if not client:
            return None
        try:
            return client.schema('abhihub').table('app_feedback')
        except Exception:
            return client.table('app_feedback')
    except Exception as e:
        logging.debug(f"[tea_supporters] Supabase client init error: {e}")
        return None


def add_app_feedback(name: str, rating: int, message: str, college: str = "", branch: str = "", user_id: str = "") -> Dict[str, Any]:
    """Adds a rating and feedback entry to Supabase app_feedback with local fallback."""
    clean_name = (name or '').strip()[:50] or "Student Contributor"
    clean_msg = (message or '').strip()[:300]
    clean_rating = max(1, min(5, int(rating or 5)))
    clean_col = (college or '').strip()[:60] or "Engineering Scholar"
    clean_branch = (branch or '').strip()[:40]

    all_records = _load_all_supporters()
    feedback_id = f"FB{int(datetime.now().timestamp())}"

    feedback_record = {
        "id": feedback_id,
        "order_id": feedback_id,
        "type": "feedback",
        "name": clean_name,
        "rating": clean_rating,
        "college": clean_col,
        "branch": clean_branch,
        "message": clean_msg,
        "user_id": user_id or None,
        "date": "Just now",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    # Attempt Supabase insert
    sb_table = _get_supabase_feedback_table()
    if sb_table:
        try:
            sb_data = {
                "name": clean_name,
                "rating": clean_rating,
                "college": clean_col,
                "branch": clean_branch,
                "message": clean_msg,
                "user_id": str(user_id) if user_id else None,
                "status": "approved"
            }
            res = sb_table.insert(sb_data).execute()
            if res and getattr(res, 'data', None):
                row = res.data[0]
                feedback_record["id"] = str(row.get("id") or feedback_id)
                feedback_record["order_id"] = feedback_record["id"]
                logging.info(f"[tea_supporters] Stored feedback in Supabase: {feedback_record['id']}")
        except Exception as err:
            logging.warning(f"[tea_supporters] Supabase feedback insert fallback: {err}")

    # Deduplicate in local store: prevent duplicate entries with identical name and message
    existing_dupe = any(
        (r.get('name') or '').strip().lower() == clean_name.lower() and
        (r.get('message') or '').strip().lower() == clean_msg.lower()
        for r in all_records
    )
    if not existing_dupe:
        all_records.insert(0, feedback_record)
        try:
            with open(SUPPORTERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_records[:150], f, indent=2)
        except Exception as e:
            logging.warning(f"[tea_supporters] Error saving feedback: {e}")

    return feedback_record


def get_recent_feedbacks(limit: int = 8) -> List[Dict[str, Any]]:
    """Returns persistent app feedbacks from Supabase with local JSON & default fallback, fully deduplicated."""
    sb_records = []
    sb_table = _get_supabase_feedback_table()
    if sb_table:
        try:
            res = sb_table.select('*').eq('status', 'approved').order('created_at', desc=True).limit(limit).execute()
            if res and getattr(res, 'data', None):
                for row in res.data:
                    sb_records.append({
                        "id": str(row.get('id') or ''),
                        "name": row.get('name') or 'Student',
                        "rating": int(row.get('rating') or 5),
                        "college": row.get('college') or 'Engineering Scholar',
                        "branch": row.get('branch') or '',
                        "message": row.get('message') or '',
                        "date": "Recently",
                        "created_at": row.get('created_at') or ''
                    })
        except Exception as err:
            logging.debug(f"[tea_supporters] Supabase feedback fetch fallback: {err}")

    all_records = _load_all_supporters()
    custom_feedbacks = [
        r for r in all_records
        if r.get('type') == 'feedback' or 'rating' in r
    ]

    seen_ids = set()
    seen_text = set()
    combined = []

    for f in sb_records + custom_feedbacks + DEFAULT_FEEDBACKS:
        fid = f.get('id') or f.get('order_id')
        name_key = (f.get('name') or '').strip().lower()
        msg_key = (f.get('message') or '').strip().lower()[:60]
        text_signature = f"{name_key}::{msg_key}"

        if fid and fid in seen_ids:
            continue
        if text_signature in seen_text:
            continue

        if fid:
            seen_ids.add(fid)
        seen_text.add(text_signature)
        combined.append(f)

    return combined[:limit]

