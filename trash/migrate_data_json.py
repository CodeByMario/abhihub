import json
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client, ClientOptions

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY").strip("'").strip('"')

import supabase
supabase_client: Client = create_client(
    url, 
    key, 
    options=ClientOptions(
        schema="abhihub"
    )
)
# Force set the Auth header on the underlying postgrest client just in case
supabase_client.postgrest.auth(key)

def migrate_data():
    print("Migrating data.json to abhihub.documents...")
    try:
        with open('data/data.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("data/data.json not found, skipping...")
        return

    records_to_insert = []
    for item in data:
        # Determine status
        status = 'approved' if item.get('verified') else 'pending'
        
        # Build description with extra metadata
        metadata = {}
        if item.get('author'):
            metadata['author'] = item.get('author')
        if item.get('year'):
            metadata['year'] = item.get('year')
        if item.get('subject'):
            metadata['subject'] = item.get('subject')
        if item.get('exam'):
            metadata['exam'] = item.get('exam')
        
        # We must make sure required fields are present
        title = item.get('file-name', 'Unknown Title')
        document_category = item.get('type', 'Other')
        file_url = item.get('file-path', '')
        
        if not file_url:
            print(f"Skipping record without file_url: {title}")
            continue

        record = {
            "title": title[:255], # Ensure title isn't ridiculously long
            "document_category": document_category[:255],
            "description": json.dumps(metadata) if metadata else None,
            "file_url": file_url,
            "storage_provider": "firebase", # inferred default
            "file_type": item.get("file-type", "unknown"),
            "status": status,
        }
        
        # Add dates if valid
        if item.get('date_added'):
            record['created_at'] = item.get('date_added')

        records_to_insert.append(record)

    # Insert in batches to avoid payload size limits
    batch_size = 500
    total_inserted = 0
    for i in range(0, len(records_to_insert), batch_size):
        batch = records_to_insert[i:i+batch_size]
        try:
            res = supabase_client.from_('documents').insert(batch).execute()
            total_inserted += len(batch)
            print(f"Inserted {total_inserted}/{len(records_to_insert)} records...")
        except Exception as e:
            # Let's see the full error dict to know if it's RLS or foreign key
            if hasattr(e, 'message'):
                 print(f"Failed to insert batch {i//batch_size}. Message: {e.message}")
            elif hasattr(e, 'args'):
                 print(f"Failed to insert batch {i//batch_size}. Args: {e.args}")
            else:
                 print(f"Failed to insert batch {i//batch_size}: {e}")
            break

    print(f"Migration completed. Total records inserted: {total_inserted}")

if __name__ == "__main__":
    migrate_data()
