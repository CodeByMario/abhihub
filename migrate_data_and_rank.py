import os
import json
from methods.supabase_helper import init_supabase

def migrate():
    print("Initializing Supabase...")
    client = init_supabase()
    if not client:
        print("Failed to initialize Supabase.")
        return

    data_file = os.path.join("static", "premium", "data.json")
    rank_file = os.path.join("static", "premium", "rank.json")

    print(f"Reading {data_file}...")
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {data_file}: {e}")
        return

    print(f"Read {len(data)} documents from data.json.")
    
    print("Wiping existing documents in abhihub.documents...")
    try:
        # Warning: This is a destructive operation. We delete all, but Supabase doesn't easily allow DELETE without filters.
        # So we delete where id is not null.
        client.table('documents').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
        print("Wipe complete.")
    except Exception as e:
        print(f"Error wiping documents: {e}")

    print("Migrating documents...")
    inserted = 0
    # Process in batches of 100 to avoid payload size issues
    batch_size = 100
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        payload = []
        for item in batch:
            # Map legacy data fields to Supabase document columns
            file_name = item.get('file-name', 'Unknown')
            file_path = item.get('file-path', '')
            file_type = item.get('file-type', '')
            doc_category = item.get('type', 'Other')
            verified = item.get('verified', False)
            status = item.get('status', False) # Some use 'status' instead of 'verified'
            is_approved = verified or status
            
            # Additional metadata for description json
            author = item.get('author', '')
            subject = item.get('subject', '')
            year = item.get('year', '')
            exam = item.get('exam', '')
            
            desc_json = {
                'author': author,
                'subject': subject,
                'year': year,
                'exam': exam
            }
            
            payload_item = {
                'title': file_name,
                'file_url': file_path,
                'storage_provider': 'firebase',
                'status': 'approved' if is_approved else 'pending',
                'document_category': doc_category,
                'file_type': file_type,
                'description': json.dumps(desc_json)
            }
            payload.append(payload_item)
            
        try:
            client.table('documents').insert(payload).execute()
            inserted += len(payload)
            print(f"Inserted {inserted}/{len(data)} documents...")
        except Exception as e:
            print(f"Error inserting batch: {e}")
            break

    print(f"Document migration complete. Total inserted: {inserted}")

    print(f"Reading {rank_file}...")
    try:
        with open(rank_file, 'r', encoding='utf-8') as f:
            rank_data = json.load(f)
    except Exception as e:
        print(f"Error reading {rank_file}: {e}")
        return

    print(f"Read {len(rank_data)} ranks.")
    print("Migrating ranks to profiles...")
    ranks_updated = 0
    for rank in rank_data:
        author = rank.get('author')
        points = rank.get('points', 0)
        if author:
            try:
                # Update profiles where full_name matches author
                # Since full_name isn't necessarily unique this might update multiple, which is acceptable
                res = client.table('profiles').update({'reputation_score': int(points)}).eq('full_name', author).execute()
                ranks_updated += len(res.data) if res.data else 0
            except Exception as e:
                print(f"Error updating rank for {author}: {e}")

    print(f"Rank migration complete. Profiles updated with reputation points: {ranks_updated}")

if __name__ == "__main__":
    migrate()
