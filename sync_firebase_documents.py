"""
Sync Firebase Storage files → abhihub.documents table.

Lists all files from Firebase Storage, compares with existing
abhihub.documents records, and inserts any missing ones with
metadata extracted from the file path + random uploader assignment.
"""

import os
import json
import random
from dotenv import load_dotenv
from supabase import create_client, Client, ClientOptions

# ── Firebase ────────────────────────────────────────────────────────────────
import firebase_admin
from firebase_admin import credentials, storage as fb_storage

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# ── Supabase clients ───────────────────────────────────────────────────────
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")
if key:
    key = key.strip("'").strip('"')

if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not found!")
    exit(1)

opts = ClientOptions(schema="abhihub", persist_session=False, auto_refresh_token=False)
supabase: Client = create_client(url, key, options=opts)

# ── Firebase init ───────────────────────────────────────────────────────────
firebase_service_account = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
if not firebase_admin._apps:
    if firebase_service_account:
        cred = credentials.Certificate(json.loads(firebase_service_account))
    else:
        cred = credentials.Certificate("firebase-auth.json")
    firebase_admin.initialize_app(cred, {'storageBucket': 'abhi-hub.appspot.com'})

bucket = fb_storage.bucket()


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def fetch_all_firebase_files():
    """List every file in the Firebase Storage bucket."""
    print("Listing all files in Firebase Storage…")
    blobs = bucket.list_blobs(prefix="Documents/")
    files = [b.name for b in blobs if not b.name.endswith('/')]
    print(f"  Found {len(files)} files in Firebase Storage.")
    return files


def load_data_json():
    """Load data/data.json into a dict keyed by file-path."""
    try:
        with open(os.path.join(os.path.dirname(__file__), 'data', 'data.json'), 'r') as f:
            records = json.load(f)
        return {r['file-path']: r for r in records}
    except Exception as e:
        print(f"  Warning: Could not load data.json: {e}")
        return {}


def fetch_existing_firebase_docs():
    """Return set of file_url values already in abhihub.documents with provider=firebase."""
    existing = set()
    try:
        res = supabase.table('documents') \
            .select('file_url') \
            .eq('storage_provider', 'firebase') \
            .execute()
        for row in (res.data or []):
            existing.add(row['file_url'])
    except Exception as e:
        print(f"  Warning: Could not fetch existing documents: {e}")
    print(f"  {len(existing)} Firebase documents already in abhihub.documents.")
    return existing


def fetch_profiles():
    """Return list of profile UUIDs to use for random uploader assignment."""
    try:
        res = supabase.table('profiles').select('id').execute()
        ids = [r['id'] for r in (res.data or [])]
        print(f"  Loaded {len(ids)} profiles for random assignment.")
        return ids
    except Exception as e:
        print(f"  Warning: Could not load profiles: {e}")
        return []


def fetch_colleges():
    """Return dict: lowercase college name → UUID."""
    try:
        res = supabase.table('colleges').select('id, name, abbreviation').execute()
        mapping = {}
        for c in (res.data or []):
            mapping[c['name'].lower()] = c['id']
            if c.get('abbreviation'):
                mapping[c['abbreviation'].lower()] = c['id']
        return mapping
    except Exception as e:
        print(f"  Warning: Could not load colleges: {e}")
        return {}


def fetch_departments():
    """Return dict: lowercase dept name → UUID, plus first department as default."""
    try:
        res = supabase.table('departments').select('id, name').execute()
        mapping = {}
        for d in (res.data or []):
            mapping[d['name'].lower()] = d['id']
        return mapping
    except Exception as e:
        print(f"  Warning: Could not load departments: {e}")
        return {}


def fetch_subjects():
    """Return dict: lowercase subject name/code → UUID."""
    try:
        res = supabase.table('subjects').select('id, name, subject_code').execute()
        mapping = {}
        for s in (res.data or []):
            mapping[s['name'].lower()] = s['id']
            if s.get('subject_code'):
                mapping[s['subject_code'].lower()] = s['id']
        return mapping
    except Exception as e:
        print(f"  Warning: Could not load subjects: {e}")
        return {}


def path_contains_bhushan(file_path: str) -> bool:
    return 'bhushan' in file_path.lower()


def extract_metadata(file_path: str, data_json_map: dict):
    """
    Extract metadata from a Firebase file path.

    Path format: Documents/<Author>/<Type>/<Year>/<Subject>/<filename.ext>
    or AbhiHub style: Documents/AbhiHub/<Type>/<Subject>/<filename.ext>
    """
    parts = file_path.split('/')
    filename_with_ext = parts[-1] if parts else ''
    name_parts = filename_with_ext.rsplit('.', 1)
    title = name_parts[0] if name_parts else filename_with_ext
    file_type = name_parts[1] if len(name_parts) > 1 else ''

    author = parts[1] if len(parts) > 1 else ''
    doc_type = parts[2] if len(parts) > 2 else ''
    year = parts[3] if len(parts) > 3 else ''
    subject = parts[4] if len(parts) > 4 else ''

    # Use data.json metadata if available (richer info)
    dj = data_json_map.get(file_path, {})
    if dj:
        title = dj.get('file-name', title)
        file_type = dj.get('file-type', file_type)
        doc_type = dj.get('type', doc_type) or doc_type
        year = dj.get('year', year) or year
        subject = dj.get('subject', subject) or subject
        author = dj.get('author', author) or author

    return {
        'title': title,
        'file_type': file_type,
        'document_category': doc_type or 'Other',
        'year': year,
        'subject': subject,
        'author': author,
        'verified': dj.get('verified', False),
        'date_added': dj.get('date_added'),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def sync():
    print("=" * 60)
    print("  Firebase → abhihub.documents Sync")
    print("=" * 60)

    # 1. Gather data
    fb_files = fetch_all_firebase_files()
    existing_urls = fetch_existing_firebase_docs()
    data_json_map = load_data_json()
    profiles = fetch_profiles()
    colleges = fetch_colleges()
    departments = fetch_departments()
    subjects = fetch_subjects()

    # Defaults
    default_college_id = next(iter(colleges.values()), None)
    default_dept_id = next(iter(departments.values()), None)

    # PCE college lookup / creation
    pce_college_id = colleges.get('pce') or colleges.get('pillai college of engineering')
    if not pce_college_id:
        # Create PCE if it doesn't exist yet
        try:
            res = supabase.table('colleges').upsert({
                'name': 'Pillai College of Engineering',
                'abbreviation': 'PCE',
            }, on_conflict='name').execute()
            if res.data:
                pce_college_id = res.data[0]['id']
                print(f"  Created/found PCE college: {pce_college_id}")
        except Exception as e:
            print(f"  Warning: Could not create PCE college: {e}")
            pce_college_id = default_college_id

    # 2. Find missing files
    missing = [f for f in fb_files if f not in existing_urls]

    # Also check data.json entries that might not be in Firebase listing
    for path in data_json_map:
        if path not in existing_urls and path not in missing:
            missing.append(path)

    print(f"\n  Total Firebase files:           {len(fb_files)}")
    print(f"  Already in abhihub.documents:   {len(existing_urls)}")
    print(f"  Missing (to be inserted):       {len(missing)}")

    if not missing:
        print("\n✅ All files are already synced!")
        return

    if not profiles:
        print("\n⚠️  No profiles found – uploader_id will be NULL for all records.")

    # 3. Build insert records
    batch = []
    errors = 0

    for fp in missing:
        try:
            meta = extract_metadata(fp, data_json_map)

            # College assignment
            if path_contains_bhushan(fp):
                c_id = pce_college_id
            else:
                c_id = default_college_id

            # Subject lookup
            s_id = None
            if meta['subject']:
                s_id = subjects.get(meta['subject'].lower().strip())

            # Random uploader
            uploader = random.choice(profiles) if profiles else None

            record = {
                'uploader_id': uploader,
                'college_id': c_id,
                'department_id': default_dept_id,
                'subject_id': s_id,
                'title': meta['title'],
                'document_category': meta['document_category'],
                'description': f"Year: {meta['year']} | Author: {meta['author']}",
                'file_url': fp,
                'storage_provider': 'firebase',
                'file_type': meta['file_type'],
                'status': 'approved' if meta['verified'] else 'pending',
                'created_at': meta['date_added'],
            }
            batch.append(record)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error building record for {fp}: {e}")

    # 4. Insert in chunks
    inserted = 0
    chunk_size = 100
    for i in range(0, len(batch), chunk_size):
        chunk = batch[i:i + chunk_size]
        try:
            res = supabase.table('documents').insert(chunk).execute()
            if res.data:
                inserted += len(res.data)
                print(f"  Inserted chunk {i // chunk_size + 1}: {len(res.data)} records")
        except Exception as e:
            print(f"  Error inserting chunk {i // chunk_size + 1}: {e}")
            # Try inserting one-by-one for this chunk to pinpoint issues
            for rec in chunk:
                try:
                    r = supabase.table('documents').insert(rec).execute()
                    if r.data:
                        inserted += 1
                except Exception as inner_e:
                    errors += 1
                    if errors <= 10:
                        print(f"    Failed: {rec['title']} – {inner_e}")

    # 5. Summary
    print(f"\n{'=' * 60}")
    print(f"  ✅ Inserted:  {inserted}")
    print(f"  ❌ Errors:    {errors}")
    print(f"  Total docs now (approx): {len(existing_urls) + inserted}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    sync()
