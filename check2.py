import os
import sys
sys.path.append('e:/code/projects/abhiHub/abhihub/abhi-hub/')
from methods.supabase_helper import init_supabase

client = init_supabase()
res = client.table('documents').select('title, status, created_at, uploader_id').order('created_at', desc=True).limit(5).execute()
for doc in res.data:
    print(f"{doc.get('title')} - {doc.get('status')} - {doc.get('created_at')} - {doc.get('uploader_id')}")
