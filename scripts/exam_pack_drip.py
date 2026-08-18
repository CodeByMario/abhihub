#!/usr/bin/env python3
"""
exam_pack_drip.py — Send the exam-pack / referral re-engagement email to a segment.

Provider-agnostic. Picks the first configured provider from env:
  GMAIL_SMTP  -> Gmail SMTP (app password)      [GMAIL_USER, GMAIL_APP_PASSWORD]
  BREVO_API_KEY -> Brevo transactional email     [BREVO_API_KEY, BREVO_SENDER]
  RESEND_API_KEY -> Resend                       [RESEND_API_KEY, RESEND_SENDER]

Always supports --dry-run (default) so you can preview every email without sending.

Usage:
  # preview
  python scripts/exam_pack_drip.py --segment dormant --dry-run
  # actually send (only after configuring a provider in .env)
  python scripts/exam_pack_drip.py --segment dormant --send
  python scripts/exam_pack_drip.py --csv exports/users_new.csv --send

Template variables: {{name}}, {{referral_code}}, {{join_url}}, {{exam_pack_url}}
"""
import argparse
import csv
import os
import smtplib
import sys
import json
import urllib.request
from email.message import EmailMessage

# Load .env so GMAIL_*/BREVO_*/RESEND_* (and BASE_DOMAIN) are visible via os.getenv.
def _load_env():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

BASE_DOMAIN = os.getenv('BASE_DOMAIN', 'abhihub.edu.eu.org').strip().lower()
JOIN_URL = f"https://{BASE_DOMAIN}/signup"
EXAM_PACK_URL = f"https://{BASE_DOMAIN}/pyq"

# Sender identity — campaign goes out as info@<your domain>
FROM_EMAIL = os.getenv('CAMPAIGN_FROM', f'info@{BASE_DOMAIN}')
FROM_NAME = os.getenv('CAMPAIGN_FROM_NAME', 'AbhiHub')

SUBJECT = "📚 Your branch exam pack is ready on AbhiHub"

HTML = """\
<!doctype html>
<html><body style="font-family:Poppins,Arial,sans-serif;max-width:480px;margin:0 auto;padding:20px">
  <h2>Hi {{name}} 👋</h2>
  <p>Semester-end is close. We pulled together the <b>previous-year question papers</b> and
     toppers' notes your branch actually needs — all free, on AbhiHub.</p>
  <p style="text-align:center;margin:24px 0">
    <a href="{{exam_pack_url}}" style="background:#10b981;color:#fff;padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:700">
      Get your exam pack →</a>
  </p>
  <p>Sharing helps you too: invite a classmate with your code
     <b>{{referral_code}}</b> and you both earn <b>50 credits</b>.</p>
  <p style="text-align:center;margin:18px 0">
    <a href="{{join_url}}?ref={{referral_code}}" style="color:#4f46e5;font-weight:700;text-decoration:none">
      Invite & earn →</a>
  </p>
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
  <p style="font-size:12px;color:#94a3b8">AbhiHub — student-driven study resources.
     You received this because you have an AbhiHub account.</p>
</body></html>"""

TEXT = """\
Hi {{name}},

Semester-end is close. Your branch's previous-year papers and toppers' notes are ready — free on AbhiHub:
{{exam_pack_url}}

Sharing helps: invite a classmate with your code {{referral_code}} and you both earn 50 credits.
Invite & earn: {{join_url}}?ref={{referral_code}}

— AbhiHub
"""

def render(tpl, name, code):
    return (tpl
            .replace('{{name}}', name)
            .replace('{{referral_code}}', code)
            .replace('{{join_url}}', JOIN_URL)
            .replace('{{exam_pack_url}}', EXAM_PACK_URL))

def load_rows(path):
    rows = []
    with open(path, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows

def send_gmail(to, name, code):
    user = os.getenv('GMAIL_USER')
    # Gmail app passwords are 16 alphanumeric chars; Google displays them with
    # spaces (e.g. "poqt efgh ijkl mnop"). Strip all whitespace before use.
    pw = (os.getenv('GMAIL_APP_PASSWORD') or '').replace(' ', '').replace('\t', '')
    msg = EmailMessage()
    msg['Subject'] = SUBJECT
    msg['From'] = f'{FROM_NAME} <{FROM_EMAIL}>'
    msg['To'] = to
    msg.set_content(render(TEXT, name, code))
    msg.add_alternative(render(HTML, name, code), subtype='html')
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(user, pw)
        s.send_message(msg)

def send_brevo(to, name, code):
    import urllib.request as u
    key = os.getenv('BREVO_API_KEY')
    sender = os.getenv('BREVO_SENDER', FROM_EMAIL)
    payload = json.dumps({
        'sender': {'name': FROM_NAME, 'email': sender},
        'to': [{'email': to}],
        'subject': SUBJECT,
        'textContent': render(TEXT, name, code),
        'htmlContent': render(HTML, name, code),
    }).encode()
    req = urllib.request.Request('https://api.brevo.com/v3/smtp/email', data=payload,
                                  headers={'api-key': key, 'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=30)

def send_resend(to, name, code):
    key = os.getenv('RESEND_API_KEY')
    sender = os.getenv('RESEND_SENDER', FROM_EMAIL)
    payload = json.dumps({
        'from': f'{FROM_NAME} <{sender}>', 'to': [to], 'subject': SUBJECT,
        'text': render(TEXT, name, code), 'html': render(HTML, name, code),
    }).encode()
    req = urllib.request.Request('https://api.resend.com/emails', data=payload,
                                 headers={'Authorization': f'Bearer {key}',
                                          'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=30)

def get_sender():
    if os.getenv('GMAIL_APP_PASSWORD'):
        return 'gmail', send_gmail
    if os.getenv('BREVO_API_KEY'):
        return 'brevo', send_brevo
    if os.getenv('RESEND_API_KEY'):
        return 'resend', send_resend
    return None, None

def clean_name(raw, email=''):
    """Derive a friendly first name for the greeting.

    Handles: real names ('Niranjan Samantaray' -> 'Niranjan'),
    email-handle full_names ('mahi.jhawar.etc' -> 'Mahi'),
    and missing names (falls back to email local-part -> capitalized).
    """
    import re
    raw = (raw or '').strip()
    # Use email local-part whenever the name is empty or looks like an email/handle
    if (not raw) or ('@' in raw) or ('.' in raw) or ('_' in raw) or raw.islower():
        local = (email.split('@')[0] if '@' in email else raw) or 'there'
        first = re.split(r'[._\-]', local)[0]
        first = re.sub(r'\d+', '', first)
        return first[:20].title() or 'there'
    # Genuine spaced name: take the first word, title-cased
    return raw.split()[0].strip().title()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--segment', default='dormant', help='which exports/users_<seg>.csv')
    ap.add_argument('--csv', default='', help='explicit CSV path (overrides --segment)')
    ap.add_argument('--dry-run', action='store_true', help='preview only (default behaviour; explicit flag)')
    ap.add_argument('--test', action='store_true', help='send ONE test email to validate SMTP credentials/deliverability')
    ap.add_argument('--send', action='store_true', help='actually send (default is dry-run)')
    args = ap.parse_args()

    path = args.csv or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'exports', f'users_{args.segment}.csv')
    if not os.path.exists(path):
        print(f'CSV not found: {path}', file=sys.stderr)
        sys.exit(1)

    rows = load_rows(path)
    provider, sender = get_sender()

    print(f"Loaded {len(rows)} recipients from {path}")
    if args.send or args.test:
        if not sender:
            print('ERROR: no email provider configured (set GMAIL_*/BREVO_*/RESEND_* in .env)',
                  file=sys.stderr)
            sys.exit(1)
        # Pre-flight credential sanity check (Gmail)
        if provider == 'gmail':
            pw = os.getenv('GMAIL_APP_PASSWORD', '').replace(' ', '').replace('\t', '')
            if len(pw) != 16 or not pw.isalnum():
                print('ERROR: GMAIL_APP_PASSWORD does not look like a 16-char Gmail App Password.')
                print('  Fix: Google Account → Security → App Passwords → create one (2-Step Verification must be ON).')
                print('  Then set GMAIL_APP_PASSWORD=<16-char code> in .env (spaces are auto-stripped).')
                sys.exit(1)
        if args.test:
            # Send a single test email to the first valid recipient (or the Gmail user)
            test_to = next((r.get('email') for r in rows if r.get('email')), os.getenv('GMAIL_USER'))
            try:
                sender(test_to, clean_name(rows[0].get('full_name'), test_to), rows[0].get('referral_code') or 'ABHI-TEST')
                print(f"TEST SEND OK -> {test_to}")
            except Exception as e:
                print(f"TEST SEND FAILED: {e}")
                print('  If 535/5.7.8 BadCredentials: the App Password is wrong/revoked. Regenerate it.')
            sys.exit(0)
        print(f"SENDING via {provider} ...")
    else:
        print("DRY-RUN (no emails sent). Sample preview:")

    sent = 0
    for i, r in enumerate(rows):
        name = clean_name(r.get('full_name'), r.get('email') or '')
        code = r.get('referral_code') or 'ABHI-JOIN'
        to = r.get('email')
        if not to:
            continue
        if args.send:
            try:
                sender(to, name, code)
                sent += 1
            except Exception as e:
                print(f"  FAIL {to}: {e}")
        else:
            if i < 3:
                print(f"\n--- to {to} (name={name}, code={code}) ---")
                print(render(TEXT, name, code)[:220])
    if args.send:
        print(f"Sent {sent}/{len(rows)}")
    else:
        print(f"\nDry-run complete. Run with --send to deliver to all {len(rows)} recipients.")

if __name__ == '__main__':
    main()
