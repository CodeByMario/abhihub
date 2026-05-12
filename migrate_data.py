import json
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client, ClientOptions

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY").strip("'").strip('"')
supabase: Client = create_client(url, key, options=ClientOptions(schema="abhihub"))

def get_user_id_by_email(email):
    """Attempt to find user profile ID by email."""
    if email == "unknown" or not email:
        return None
    try:
        response = supabase.schema('abhihub').from_('profiles').select('id').eq('email', email).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]['id']
    except Exception as e:
        print(f"Error fetching user for email {email}: {e}")
    return None

def migrate_suspects():
    print("Migrating suspects.json to security_audit_logs...")
    try:
        with open('data/suspects.json', 'r') as f:
            suspects = json.load(f)
    except FileNotFoundError:
        print("data/suspects.json not found, skipping...")
        return

    records_to_insert = []
    for s in suspects:
        # Map JSON action to SQL enum
        event_map = {
            "right_click": "right_click_prevented",
            "mobile_screenshot": "screenshot_detected",
            "printscreen_key": "screenshot_detected"
        }
        event = event_map.get(s.get("action"), "unauthorized_access")
        
        # Determine user_id
        user_id = None
        if s.get("uid") != "anonymous":
            user_id = s.get("uid")
        elif s.get("email") != "unknown":
            user_id = get_user_id_by_email(s.get("email"))

        record = {
            "user_id": user_id,
            "event": event,
            "ip_address": s.get("ip"),
            "metadata": {"name": s.get("name"), "original_action": s.get("action")},
            "detected_at": s.get("timestamp")
        }
        records_to_insert.append(record)

    if records_to_insert:
        try:
            res = supabase.schema('abhihub').from_('security_audit_logs').insert(records_to_insert).execute()
            print(f"Successfully migrated {len(records_to_insert)} suspect records.")
        except Exception as e:
            print(f"Failed to insert suspects: {e}")
    else:
        print("No suspect records to migrate.")

def migrate_push_subscriptions():
    print("Migrating push_subscriptions.json to push_subscriptions table...")
    try:
        with open('data/push_subscriptions.json', 'r') as f:
            subs = json.load(f)
    except FileNotFoundError:
        print("data/push_subscriptions.json not found, skipping...")
        return

    records_to_insert = []
    for email, data in subs.items():
        user_id = None
        if email != "anonymous":
            user_id = get_user_id_by_email(email)
            if not user_id:
               print(f"Warning: Could not find user_id for email {email}. Skipping subscription.")
               continue
        else:
            print("Warning: anonymous push subscriptions cannot be tied to a foreign key in users correctly without an ID. Skipping.")
            continue
            
        repo = data.get("subscription", {})
        keys = repo.get("keys", {})
        
        # Check if subscription already exists using endpoint (must be unique)
        try:
             existing = supabase.schema('abhihub').from_('push_subscriptions').select('id').eq('endpoint', repo.get("endpoint")).execute()
             if existing.data:
                 print(f"Subscription for {email} already exists, skipping...")
                 continue
        except Exception as e:
            pass

        record = {
            "user_id": user_id,
            "endpoint": repo.get("endpoint"),
            "p256dh": keys.get("p256dh"),
            "auth": keys.get("auth"),
            "created_at": data.get("created_at")
        }
        records_to_insert.append(record)

    if records_to_insert:
        try:
            res = supabase.schema('abhihub').from_('push_subscriptions').insert(records_to_insert).execute()
            print(f"Successfully migrated {len(records_to_insert)} push subscription records.")
        except Exception as e:
            print(f"Failed to insert push subscriptions: {e}")
    else:
        print("No new push subscription records to migrate.")

if __name__ == "__main__":
    print(f"Starting migration to Supabase schema 'abhihub'...")
    migrate_suspects()
    migrate_push_subscriptions()
    print("Migration finished!")
