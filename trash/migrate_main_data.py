import os
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client, ClientOptions

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")
if key:
    key = key.strip("'").strip('"')

if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not found in environment!")
    exit(1)

opts_public = ClientOptions(schema="public", persist_session=False, auto_refresh_token=False)
opts_abhihub = ClientOptions(schema="abhihub", persist_session=False, auto_refresh_token=False)

supabase_public: Client = create_client(url, key, options=opts_public)
supabase_abhihub: Client = create_client(url, key, options=opts_abhihub)

def get_all(table, client):
    all_data = []
    # Simplified fetch, assuming less than 1000 rows per table for this scale
    try:
        res = client.table(table).select("*").execute()
        if res.data:
            all_data.extend(res.data)
    except Exception as e:
        import traceback
        print(f"\n[!] Error fetching {table}: {e}", flush=True)
        traceback.print_exc()
        # Return empty list instead of raising to see which table fails
    return all_data

def migrate():
    print("Starting Main Data Migration...", flush=True)

    # Fetch source data
    print("Fetching source data...", flush=True)
    public_colleges = get_all('college', supabase_public)
    public_branches = get_all('branch', supabase_public)
    public_subjects = get_all('subject', supabase_public)
    public_students = get_all('students', supabase_public)
    public_file_records = get_all('file_records', supabase_public)
    public_cae1 = get_all('cae1', supabase_public)
    public_cae2 = get_all('cae2', supabase_public)
    public_cae3 = get_all('cae3', supabase_public)
    public_ese = get_all('ese', supabase_public)
    
    # Also fetch data.json
    data_json = []
    try:
        with open('data/data.json', 'r') as f:
            data_json = json.load(f)
    except Exception as e:
        print(f"Error loading data.json: {e}")

    print(f"Loaded: Colleges ({len(public_colleges)}), Branches ({len(public_branches)}), Subjects ({len(public_subjects)})")
    print(f"Loaded: Students ({len(public_students)}), File Records ({len(public_file_records)})")
    print(f"Loaded: CAE1 ({len(public_cae1)}), CAE2 ({len(public_cae2)}), CAE3 ({len(public_cae3)}), ESE ({len(public_ese)})")
    print(f"Loaded: data.json records ({len(data_json)})")

    # Mappings
    college_map = {} # old bigint -> new UUID
    branch_map = {} # old bigint -> new UUID
    subject_map = {} # old uuid -> new UUID

    # MIGRATION 1: Colleges
    print("\nMigrating Colleges...")
    for c in public_colleges:
        c_name = c.get('college_name') or c.get('name')
        if not c_name: continue
        try:
            res = supabase_abhihub.table('colleges').upsert({
                'name': c_name,
                'abbreviation': c.get('college_abbreviation') or c.get('short_name'),
                'city': c.get('city'),
                'created_at': c.get('created_at'),
                'updated_at': c.get('updated_at') or c.get('created_at')
            }, on_conflict='name').execute()
            if res.data:
                college_map[c['id']] = res.data[0]['id']
                print(f"  Inserted College: {c_name} -> {res.data[0]['id']}", flush=True)
        except Exception as e:
            print(f"  Failed to insert College {c_name}: {e}", flush=True)

    # Get the default college ID
    default_college_id = list(college_map.values())[0] if college_map else None

    # MIGRATION 2: Departments (Branches)
    print("\nMigrating Branches to Departments...")
    for b in public_branches:
        b_name = b.get('branch_name') or b.get('name')
        if not b_name: continue
        res = supabase_abhihub.table('departments').upsert({
            'college_id': default_college_id, # Assuming all branches belong to the default college
            'name': b_name,
            'abbreviation': b.get('branch_abbreviation') or b.get('short_name'),
            'created_at': b.get('created_at'),
            'updated_at': b.get('updated_at') or b.get('created_at')
        }, on_conflict='college_id, name').execute()
        if res.data:
            # Map by branch_id (bigint)
            b_id = b.get('branch_id')
            if b_id:
                branch_map[b_id] = res.data[0]['id']
            print(f"  Inserted Department: {b_name} -> {res.data[0]['id']}")

    default_department_id = list(branch_map.values())[0] if branch_map else None

    # MIGRATION 3: Subjects
    print("\nMigrating Subjects...")
    for s in public_subjects:
        s_name = s.get('subject_name')
        if not s_name: continue
        
        s_code = s.get('subject_code') or s_name[:5].upper()
        
        try:
            res = supabase_abhihub.table('subjects').upsert({
                'department_id': default_department_id,
                'name': s_name,
                'subject_code': s_code,
                'created_at': s.get('created_at')
            }, on_conflict='department_id, subject_code').execute()
            if res.data:
                subject_map[s['subject_id']] = res.data[0]['id']
        except Exception as e:
             print(f"  Failed Subject '{s_name}': {e}")
    print(f"  Migrated {len(subject_map)} Subjects.")

    # MIGRATION 4: Users and Students
    print("\nMigrating Students and Profiles...")
    profile_count = 0
    student_count = 0
    for st in public_students:
        user_id = st.get('user_id')
        if not user_id: continue 
        
        role = st.get('user_role') or 'student'
        email = st.get('student_email')
        
        if not email:
            print(f"  Skipping student {st.get('student_name')} with no email.")
            continue
            
        c_id = college_map.get(st.get('college_id')) or default_college_id
        d_id = branch_map.get(st.get('branch_id')) or default_department_id
        
        try:
            prof_res = supabase_abhihub.table('profiles').upsert({
                'id': user_id,
                'role': role,
                'email': email,
                'full_name': st.get('student_name'),
                'college_id': c_id,
                'department_id': d_id,
                'created_at': st.get('created_at')
            }, on_conflict='id').execute()
            if prof_res.data:
                profile_count += 1
                
            if role == 'student':
               stud_res = supabase_abhihub.table('students').upsert({
                   'profile_id': user_id,
                   'registration_number': st.get('registration_number'),
                   'pursuing_year': st.get('pursuing_year'),
                   'year_of_joining': st.get('year_of_joining'),
                   'profile_completed': st.get('profile_completed'),
                   'created_at': st.get('created_at')
               }, on_conflict='profile_id').execute()
               if stud_res.data:
                   student_count += 1
            elif role == 'teacher':
                 teacher_res = supabase_abhihub.table('teachers').upsert({
                     'profile_id': user_id,
                     'profile_completed': st.get('profile_completed'),
                     'created_at': st.get('created_at')
                 }, on_conflict='profile_id').execute()
        except Exception as e:
            print(f"  Failed User '{email}': {e}")
    print(f"  Migrated {profile_count} Profiles and {student_count} Students.")

    print("\nMigrating Documents from file_records (Cloudinary)...")
    doc_count = 0
    for fr in public_file_records:
        uploader_id = fr.get('user_id')
        if uploader_id and len(str(uploader_id)) < 36:
             uploader_id = None
             
        title = fr.get('file_name')
        doc_cat = fr.get('document_type') or 'File'
        file_url = fr.get('file_url')
        if not file_url: continue
        
        c_id = college_map.get(fr.get('college_id')) or default_college_id
        d_id = branch_map.get(fr.get('branch_id')) or default_department_id
        
        sub_id = None
        for old_sub_uuid, new_sub_uuid in subject_map.items():
            match_subj = next((s for s in public_subjects if s['subject_id'] == old_sub_uuid), None)
            if match_subj and match_subj.get('subject_name') == fr.get('subject_name'):
                sub_id = new_sub_uuid
                break

        try:
             res = supabase_abhihub.table('documents').insert({
                 'uploader_id': uploader_id,
                 'college_id': c_id,
                 'department_id': d_id,
                 'subject_id': sub_id,
                 'title': title,
                 'document_category': doc_cat,
                 'file_url': file_url,
                 'storage_provider': 'cloudinary',
                 'provider_public_id': fr.get('cloudinary_public_id'),
                 'file_type': fr.get('file_type'),
                 'file_size_bytes': fr.get('file_size'),
                 'status': 'approved', 
                 'view_count': fr.get('access_count') or 0,
                 'created_at': fr.get('uploaded_at')
             }).execute()
             if res.data:
                 doc_count += 1
        except Exception as e:
             pass
    print(f"  Migrated {doc_count} Cloudinary Documents.")

    print("\nMigrating documents from Exam Submissions (cae1, cae2, cae3, ese)...")
    exam_doc_count = 0
    def migrate_exam_submissions(records, table_name, path_key):
        nonlocal exam_doc_count
        for rec in records:
            file_url = rec.get(path_key)
            if not file_url: continue
            
            student_profile_id = None
            stud = next((s for s in public_students if s['student_id'] == rec.get('student_id')), None)
            if stud:
                student_profile_id = stud.get('user_id')
                
            c_id = college_map.get(rec.get('college_id')) or default_college_id
            sub_id = subject_map.get(rec.get('subject_id'))
            
            try:
                res = supabase_abhihub.table('documents').insert({
                    'uploader_id': student_profile_id,
                    'college_id': c_id,
                    'department_id': default_department_id,
                    'subject_id': sub_id,
                    'title': f"{table_name.upper()} Submission",
                    'document_category': table_name.upper(),
                    'file_url': file_url,
                    'storage_provider': 'supabase',
                    'status': 'approved' if rec.get('verification_status') else 'pending',
                    'created_at': rec.get('created_at')
                }).execute()
                if res.data:
                    exam_doc_count += 1
            except Exception as e:
                pass
    
    migrate_exam_submissions(public_cae1, 'cae1', 'cae1_path')
    migrate_exam_submissions(public_cae2, 'cae2', 'cae2_path')
    migrate_exam_submissions(public_cae3, 'cae3', 'cae3_path')
    migrate_exam_submissions(public_ese, 'ese', 'ese_path')
    print(f"  Migrated {exam_doc_count} Exam Documents.")

    print("\nMigrating Documents from data.json (Firebase)...")
    fb_count = 0
    profiles_lookup_by_name = {}
    try:
         for prof in supabase_abhihub.table('profiles').select('id, full_name').execute().data:
             profiles_lookup_by_name[prof['full_name'].lower().strip()] = prof['id']
    except Exception:
         pass

    # Batch inserts can be faster
    batch_inserts = []
    
    for d in data_json:
        title = d.get('file-name')
        file_url = d.get('file-path')
        if not file_url: continue
        
        author = d.get('author') or d.get('Author')
        uploader_id = None
        if author:
            uploader_id = profiles_lookup_by_name.get(author.lower().strip())
        
        sub_name = d.get('subject')
        sub_id = None
        if sub_name:
             match_subj = next((s for s in public_subjects if sub_name.lower() in (s.get('subject_name') or '').lower() or sub_name.lower() == (s.get('subject_code') or '').lower()), None)
             if match_subj:
                  sub_id = subject_map.get(match_subj.get('subject_id'))
        
        doc_cat = d.get('type') or d.get('Type') or d.get('category') or 'Notes'
        
        batch_inserts.append({
            'uploader_id': uploader_id,
            'college_id': default_college_id,
            'department_id': default_department_id,
            'subject_id': sub_id,
            'title': title,
            'description': f"Year: {d.get('year')} | Author: {author} | Exam: {d.get('exam', 'N/A')}",
            'document_category': doc_cat,
            'file_url': file_url,
            'file_type': d.get('file-type') or 'pdf',
            'storage_provider': 'firebase', 
            'status': 'approved' if d.get('verified') else 'pending',
            'created_at': d.get('date_added') or d.get('upload_date')
        })
    
    # Process batch in chunks to avoid single massive request
    chunk_size = 100
    for i in range(0, len(batch_inserts), chunk_size):
        chunk = batch_inserts[i:i+chunk_size]
        try:
             res = supabase_abhihub.table('documents').insert(chunk).execute()
             if res.data:
                 fb_count += len(res.data)
        except Exception as e:
             if i == 0:
                 print(f"  Example err: {e}")
             pass

    print(f"  Migrated {fb_count} Firebase Documents.")

    print("\nMigration Completed.")

    # Validation
    c_count = len(get_all('colleges', supabase_abhihub))
    print(f"Verification: Found {c_count} colleges in abhihub schema.")

if __name__ == "__main__":
    migrate()
