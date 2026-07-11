"""
One-off Migration Script: Backfill Search Documents
Selects all existing documents and pushes them to the search_documents queue for background indexing.
"""
import os
import sys
from dotenv import load_dotenv

# Ensure we can import from methods
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from methods.supabase_helper import init_supabase

def migrate_existing_documents():
    client = init_supabase()
    if not client:
        print("Failed to initialize Supabase client.")
        return

    print("Fetching existing documents...")
    # Fetch all approved documents to backfill
    res = client.table('documents').select('id, title, subject_id, college_id, department_id').in_('status', ['approved', 'pending']).execute()
    
    docs = res.data or []
    print(f"Found {len(docs)} documents to migrate.")
    
    success_count = 0
    for doc in docs:
        try:
            client.table('search_documents').insert({
                'file_id': doc['id'],
                'source': 'uploads',
                'subject_id': doc.get('subject_id'),
                'college_id': doc.get('college_id'),
                'department_id': doc.get('department_id'),
                'normalized_title': str(doc.get('title', '')).lower(),
                'status': 'pending'
            }).execute()
            success_count += 1
            if success_count % 50 == 0:
                print(f"Queued {success_count} documents...")
        except Exception as e:
            # Ignore duplicates if run multiple times
            if 'duplicate key' not in str(e).lower() and '23505' not in str(e):
                print(f"Error queueing document {doc['id']}: {e}")
                
    print(f"Migration complete. Successfully queued {success_count} documents for background indexing.")

if __name__ == '__main__':
    migrate_existing_documents()
