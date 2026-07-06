import os
from dotenv import load_dotenv
load_dotenv()
from methods.supabase_helper import get_all_colleges, get_college_stats, get_college_by_slug

college = get_college_by_slug('pce')
print(f"College: {college}")
if college.get('success'):
    cid = college['data']['id']
    stats = get_college_stats(cid)
    print(f"Stats for {cid}: {stats}")
