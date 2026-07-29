import os
from dotenv import load_dotenv
load_dotenv('e:/code/projects/abhiHub/abhihub/abhi-hub/.env')
from supabase import create_client, ClientOptions

url = os.environ.get('SUPABASE_URL')
key = os.environ.get('SUPABASE_SERVICE_KEY').strip().strip('\'').strip('\"')
opts_abhihub = ClientOptions(schema='abhihub', persist_session=False, auto_refresh_token=False)
supabase = create_client(url, key, options=opts_abhihub)

def count(table):
    try:
        # Just check if we can query at least one row, to confirm data exists 
        res = supabase.table(table).select('id').limit(1).execute()
        if res.data and len(res.data) > 0:
            return "Has Data"
        return "Empty"
    except Exception as e:
         return f"Error: {e}"

print('--- Abhihub Subschema Counts ---')
tables = ['colleges', 'departments', 'subjects', 'profiles', 'documents']
for t in tables:
    print(f'{t}: {count(t)}')

try:
    res = supabase.table('students').select('profile_id').limit(1).execute()
    print('students:', 'Has Data' if res.data else 'Empty')
except Exception as e:
    print('students:', f'Error: {e}')
