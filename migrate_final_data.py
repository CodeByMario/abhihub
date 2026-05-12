import os
import json
import uuid
import random
import logging
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client, ClientOptions

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Load Environment ---
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("SUPABASE_URL or SUPABASE_KEY not found in environment!")
    exit(1)

# Clean keys
SUPABASE_KEY = SUPABASE_KEY.strip("'").strip('"')

# --- Supabase Client ---
opts = ClientOptions(schema="abhihub", persist_session=False, auto_refresh_token=False)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY, options=opts)

def load_json(path):
    if not os.path.exists(path):
        logger.warning(f"File not found: {path}")
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
        return []

def get_mappings():
    logger.info("Fetching mappings from Supabase...")
    mappings = {
        'colleges': {},    # name -> id
        'departments': {}, # name -> id
        'subjects': {},   # name/code -> id
        'profiles': {},   # name -> id
    }
    
    try:
        # Colleges
        res = supabase.table('colleges').select('id, name, abbreviation').execute()
        for c in res.data:
            mappings['colleges'][c['name'].lower().strip()] = c['id']
            if c.get('abbreviation'):
                mappings['colleges'][c['abbreviation'].lower().strip()] = c['id']
        
        # Departments
        res = supabase.table('departments').select('id, name').execute()
        for d in res.data:
            mappings['departments'][d['name'].lower().strip()] = d['id']
            
        # Subjects
        res = supabase.table('subjects').select('id, name, subject_code').execute()
        for s in res.data:
            mappings['subjects'][s['name'].lower().strip()] = s['id']
            if s.get('subject_code'):
                mappings['subjects'][s['subject_code'].lower().strip()] = s['id']
                
        # Profiles (for uploader mapping)
        res = supabase.table('profiles').select('id, full_name').execute()
        for p in res.data:
            if p.get('full_name'):
                mappings['profiles'][p['full_name'].lower().strip()] = p['id']
                
    except Exception as e:
        logger.error(f"Error fetching mappings: {e}")
        
    return mappings

def migrate():
    logger.info("Starting consolidation and migration...")
    
    # 1. Load Data
    data_main = load_json('data/data.json')
    data_premium = load_json('static/premium/data.json')
    
    logger.info(f"Loaded {len(data_main)} records from data/data.json")
    logger.info(f"Loaded {len(data_premium)} records from static/premium/data.json")
    
    # 2. Deduplicate
    merged = {} # file-path -> record
    
    # Process premium first as a base
    for item in data_premium:
        fp = item.get('file-path')
        if not fp: continue
        merged[fp] = item
        
    # Process main data (override/enrich)
    for item in data_main:
        fp = item.get('file-path')
        if not fp: continue
        if fp in merged:
            # Enrich existing record
            merged[fp].update({
                'verified': item.get('verified', merged[fp].get('verified')),
                'date_added': item.get('date_added', merged[fp].get('date_added')),
                'status': item.get('status', merged[fp].get('status')),
                'subject': item.get('subject', merged[fp].get('subject')),
                'author': item.get('author', merged[fp].get('author')),
                'type': item.get('type', merged[fp].get('type')),
                'year': item.get('year', merged[fp].get('year')),
                'exam': item.get('exam', merged[fp].get('exam')),
            })
        else:
            merged[fp] = item
            
    logger.info(f"Consolidated into {len(merged)} unique records.")
    
    # 3. Get Existing URLs to avoid duplicates
    logger.info("Fetching existing URLs to avoid duplicates...")
    existing_urls = set()
    try:
        # Fetch in batches if necessary, but assuming reasonable count for now
        res = supabase.table('documents').select('file_url').execute()
        for row in (res.data or []):
            existing_urls.add(row['file_url'])
        logger.info(f"Found {len(existing_urls)} existing records in Supabase.")
    except Exception as e:
        logger.error(f"Error fetching existing URLs: {e}")

    # 4. Get Mappings
    mappings = get_mappings()
    
    # Default values
    default_college_id = next(iter(mappings['colleges'].values()), None)
    default_dept_id = next(iter(mappings['departments'].values()), None)
    
    # Special lookup for PCE (common in Bhushan's files)
    pce_id = mappings['colleges'].get('pce') or mappings['colleges'].get('pillai college of engineering')
    
    # 5. Prepare Records
    to_insert = []
    category_map = {
        'papers': 'papers',
        'pyq': 'papers',
        'notes': 'notes',
        'note': 'notes',
        'practical': 'practical',
        'practicals': 'practical',
        'syllabus': 'syllabus',
        'assisment': 'assisment',
        'assignment': 'assisment',
        'timetable': 'timetable'
    }
    
    processed_count = 0
    skipped_count = 0
    for fp, item in merged.items():
        processed_count += 1
        if fp in existing_urls:
            skipped_count += 1
            continue
            
        title = item.get('file-name', 'Unknown')
        author = item.get('author') or 'System'
        subject_name = item.get('subject')
        raw_type = str(item.get('type', 'Other')).lower()
        
        # Mapping college
        c_id = default_college_id
        if 'bhushan' in fp.lower() or 'pce' in fp.lower():
            c_id = pce_id or default_college_id
            
        # Mapping subject
        s_id = None
        if subject_name:
            s_id = mappings['subjects'].get(subject_name.lower().strip())
            
        # Mapping uploader
        u_id = mappings['profiles'].get(author.lower().strip())
        
        # Mapping category
        doc_cat = category_map.get(raw_type, 'notes') # Default to notes if unknown
        
        # Build description with metadata
        desc_parts = []
        if item.get('year'): desc_parts.append(f"Year: {item['year']}")
        if author: desc_parts.append(f"Author: {author}")
        if item.get('exam'): desc_parts.append(f"Exam: {item['exam']}")
        
        description = " | ".join(desc_parts)
        
        record = {
            "title": title[:255],
            "document_category": doc_cat,
            "description": description,
            "file_url": fp,
            "storage_provider": "firebase",
            "file_type": item.get("file-type", "unknown"),
            "status": "approved" if item.get("verified") else "pending",
            "uploader_id": u_id,
            "college_id": c_id,
            "department_id": default_dept_id,
            "subject_id": s_id,
        }
        
        # Add dates if valid
        if item.get('date_added'):
            record['created_at'] = item['date_added']
        
        to_insert.append(record)
        
    logger.info(f"Processed {processed_count} records. Skipped {skipped_count} existing ones. {len(to_insert)} new records to insert.")
    
    # 6. Batch Insert
    batch_size = 100
    inserted_count = 0
    for i in range(0, len(to_insert), batch_size):
        chunk = to_insert[i:i+batch_size]
        try:
            res = supabase.table('documents').insert(chunk).execute()
            if res.data:
                inserted_count += len(res.data)
                logger.info(f"Batch {i//batch_size + 1} complete. Total inserted: {inserted_count}")
        except Exception as e:
            logger.error(f"Error in batch {i//batch_size + 1}: {e}")
            # Try one by one to see which record is failing (e.g. check constraints)
            for r in chunk:
                try:
                    supabase.table('documents').insert(r).execute()
                    inserted_count += 1
                except Exception as inner_e:
                    logger.error(f"Failed to insert record '{r['title']}': {inner_e}")

    logger.info(f"Migration finished. Total records inserted/updated: {inserted_count}")

if __name__ == "__main__":
    migrate()
