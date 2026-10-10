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
    supporters = _load_all_supporters()
    return supporters[:limit]
