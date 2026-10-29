"""
Domain Tier Service — Strict Quota and Discount Policy
Handles email domain classification, initial signup view grants, tiered pack pricing,
and the Launch Special 90% Promotion (Registrations from 29 Oct 2026 till 8 Nov 2026 get 90% OFF for 90 days).
"""

import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Launch Promotion Window: 29 Oct 2026 to 8 Nov 2026 (23:59:59 UTC)
# Any account registering in this window receives 90% discount for their first 90 days.
PROMO_START = datetime(2026, 10, 29, 0, 0, 0, tzinfo=timezone.utc)
PROMO_END = datetime(2026, 11, 8, 23, 59, 59, tzinfo=timezone.utc)
PROMO_DURATION_DAYS = 90

# Disposable / Temporary Email Domains (0 views, 0% discount, excluded from promotions)
DISPOSABLE_DOMAINS = {
    'tempmail.com', 'temp-mail.org', '10minutemail.com', 'guerrillamail.com', 'guerrillamail.net',
    'guerrillamail.org', 'mailinator.com', 'yopmail.com', 'throwawaymail.com', 'trashmail.com',
    'dispostable.com', 'sharklasers.com', 'getairmail.com', 'fakeinbox.com', 'generator.email',
    'emailondeck.com', 'dropmail.me', 'mohmal.com', 'inboxkitten.com', 'crazymailing.com',
    'mytemp.email', 'tempail.com', 'fakemailgenerator.com', 'nada.ltd', 'getnada.com',
    'abcvg.com', 'burnermail.io', 'maildrop.cc', 'tempmailo.com', 'disposablemail.com',
    'trashmail.net', 'trashmail.me', 'mytrashmail.com', 'guerrillamailblock.com'
}

# Approved College Domains (20 views, full current flash discount)
APPROVED_COLLEGE_DOMAINS = {
    'ghrce.raisoni.net', 'raisoni.net', 'rcoem.in', 'vit.edu', 'coep.ac.in',
    'vjti.ac.in', 'iitb.ac.in', 'iitd.ac.in', 'bits-pilani.ac.in', 'mitwpu.edu.in'
}


def is_launch_promo_eligible(email: str, created_at: Any = None) -> bool:
    """
    Check if user qualifies for the 90% discount promotion:
    - Must be a genuine email (disposable domains are excluded).
    - Account registered between 29 Oct 2026 and 8 Nov 2026 (inclusive).
    - Current date is within 90 days of registration.
    """
    clean_email = str(email or '').strip().lower()
    if not clean_email or '@' not in clean_email:
        return False

    domain = clean_email.split('@')[1].strip()
    if domain in DISPOSABLE_DOMAINS or any(clean_email.endswith(f"@{d}") for d in DISPOSABLE_DOMAINS):
        return False

    now = datetime.now(timezone.utc)
    reg_dt = None

    if created_at:
        try:
            if isinstance(created_at, str):
                clean_ts = created_at.replace('Z', '+00:00')
                reg_dt = datetime.fromisoformat(clean_ts)
            elif isinstance(created_at, datetime):
                reg_dt = created_at
            if reg_dt and reg_dt.tzinfo is None:
                reg_dt = reg_dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    if reg_dt:
        if PROMO_START <= reg_dt <= PROMO_END:
            return (now - reg_dt).days <= PROMO_DURATION_DAYS
        return False
    else:
        return PROMO_START <= now <= PROMO_END


def classify_email(email: str, created_at: Any = None) -> Dict[str, Any]:
    """
    Classify user email into one of 3 tiers + check launch 90% promotion:
    - 'college': @ghrce.raisoni.net, *.raisoni.net, .edu, .ac.in, .edu.in -> 20 views
    - 'gmail': @gmail.com or standard personal email -> 5 views
    - 'disposable': temporary/disposable email -> 0 views (must pay directly), 0% discount
    """
    clean_email = str(email or '').strip().lower()
    if not clean_email or '@' not in clean_email:
        return {
            'tier': 'disposable',
            'starting_views': 0,
            'discount_pct': 0,
            'is_promo': False,
            'label': 'Temporary / Unknown Domain'
        }

    domain = clean_email.split('@')[1].strip()

    # Tier 3: Temporary / Disposable Domains (always excluded from promo)
    if domain in DISPOSABLE_DOMAINS or any(clean_email.endswith(f"@{d}") for d in DISPOSABLE_DOMAINS):
        return {
            'tier': 'disposable',
            'starting_views': 0,
            'discount_pct': 0,
            'is_promo': False,
            'label': 'Temporary Email Domain'
        }

    # Tier 1: Approved College Domains
    is_college = False
    if domain in APPROVED_COLLEGE_DOMAINS or domain.endswith('.raisoni.net'):
        is_college = True
    elif domain.endswith(('.edu', '.ac.in', '.edu.in', '.res.in')):
        is_college = True

    tier = 'college' if is_college else 'gmail'
    starting_views = 20 if is_college else 5

    # Check 90% Launch Special Promotion (29 Oct 2026 - 8 Nov 2026 for 90 days)
    promo_active = is_launch_promo_eligible(clean_email, created_at=created_at)
    if promo_active:
        return {
            'tier': tier,
            'starting_views': starting_views,
            'discount_pct': 90,
            'is_promo': True,
            'promo_days_left': 90,
            'label': ('Approved College Student' if is_college else 'Standard User') + ' • 🚀 90% Launch Special Active (90 Days)'
        }

    if is_college:
        return {
            'tier': 'college',
            'starting_views': 20,
            'discount_pct': 72,
            'is_promo': False,
            'label': 'Approved College Student'
        }

    # Standard Gmail Tier
    return {
        'tier': 'gmail',
        'starting_views': 5,
        'discount_pct': 20,
        'is_promo': False,
        'label': 'Standard User (Gmail)'
    }


def get_tiered_credit_packs(email: str, created_at: Any = None) -> Dict[int, Dict[str, Any]]:
    """
    Return pricing packs tailored to the user's email tier and promotion status:
    - Launch Promo (29 Oct - 8 Nov 2026): 90% discount for first 90 days (₹4, ₹13, ₹30, ₹70)
    - College: Full standard discount (₹19, ₹49, ₹99, ₹199)
    - Gmail: Max 20% discount (₹31, ₹99, ₹239, ₹549)
    - Disposable: 0% discount (Original full price: ₹39, ₹129, ₹299, ₹699)
    """
    info = classify_email(email, created_at=created_at)
    tier = info['tier']

    # 90% Launch Special Active
    if info.get('is_promo'):
        return {
            10: {'price': 4.0, 'views': 10, 'original': 39, 'discount': '90% OFF', 'badge': '🚀 Launch 90% OFF'},
            65: {'price': 13.0, 'views': 65, 'original': 129, 'discount': '90% OFF', 'badge': '🔥 90% Launch Special', 'bonus': '+15 Free'},
            160: {'price': 30.0, 'views': 160, 'original': 299, 'discount': '90% OFF', 'badge': '⭐ Best Value (90% OFF)', 'bonus': '+40 Free'},
            500: {'price': 70.0, 'views': 500, 'original': 699, 'discount': '90% OFF', 'badge': '👑 Pass (90% OFF)', 'bonus': '+100 Free'},
            50: {'price': 13.0, 'views': 65, 'original': 129, 'discount': '90% OFF'},
            100: {'price': 30.0, 'views': 160, 'original': 299, 'discount': '90% OFF'}
        }

    if tier == 'college':
        return {
            10: {'price': 19.0, 'views': 10, 'original': 39, 'discount': '51% OFF', 'badge': 'College Special'},
            65: {'price': 49.0, 'views': 65, 'original': 129, 'discount': '62% OFF', 'badge': '🔥 Most Popular', 'bonus': '+15 Free'},
            160: {'price': 99.0, 'views': 160, 'original': 299, 'discount': '67% OFF', 'badge': '⭐ Best Value', 'bonus': '+40 Free'},
            500: {'price': 199.0, 'views': 500, 'original': 699, 'discount': '72% OFF', 'badge': '👑 Ultimate Pass', 'bonus': '+100 Free'},
            50: {'price': 49.0, 'views': 65, 'original': 129, 'discount': '62% OFF'},
            100: {'price': 99.0, 'views': 160, 'original': 299, 'discount': '67% OFF'}
        }
    elif tier == 'gmail':
        return {
            10: {'price': 31.0, 'views': 10, 'original': 39, 'discount': '20% OFF', 'badge': 'Standard Top-Up'},
            65: {'price': 99.0, 'views': 65, 'original': 129, 'discount': '20% OFF', 'badge': '🔥 Most Popular', 'bonus': '+15 Free'},
            160: {'price': 239.0, 'views': 160, 'original': 299, 'discount': '20% OFF', 'badge': '⭐ Best Value', 'bonus': '+40 Free'},
            500: {'price': 549.0, 'views': 500, 'original': 699, 'discount': '20% OFF', 'badge': '👑 Pro Pass', 'bonus': '+100 Free'},
            50: {'price': 99.0, 'views': 65, 'original': 129, 'discount': '20% OFF'},
            100: {'price': 239.0, 'views': 160, 'original': 299, 'discount': '20% OFF'}
        }
    else:
        return {
            10: {'price': 39.0, 'views': 10, 'original': 39, 'discount': '0% OFF', 'badge': 'Direct Pay'},
            65: {'price': 129.0, 'views': 65, 'original': 129, 'discount': '0% OFF', 'badge': 'Standard'},
            160: {'price': 299.0, 'views': 160, 'original': 299, 'discount': '0% OFF', 'badge': 'Pro'},
            500: {'price': 699.0, 'views': 500, 'original': 699, 'discount': '0% OFF', 'badge': 'Pass'},
            50: {'price': 129.0, 'views': 65, 'original': 129, 'discount': '0% OFF'},
            100: {'price': 299.0, 'views': 160, 'original': 299, 'discount': '0% OFF'}
        }
