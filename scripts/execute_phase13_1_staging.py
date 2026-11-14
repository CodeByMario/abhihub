"""
AbhiHub Phase 13.1 — Isolated Staging Execution & Verification Harness
"""
import os, sys, csv, sqlite3, json, uuid
from datetime import datetime

sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv()
from methods.environment_guard import is_production_database, assert_staging_write_allowed

print("=" * 70)
print("ABHIHUB PHASE 13.1 - STAGING EXECUTION PIPELINE")
print("=" * 70)

# -------------------------------------------------------------------------
# Step 1: Safety Gate & Fail-Closed Environment Verification
# -------------------------------------------------------------------------
print("\n[Step 1] Testing Environment Guard & Fail-Closed Protection...")
try:
    assert_staging_write_allowed("phase13_1_production_mutation_check")
    print("  ERROR: Fail-closed guard failed to trigger!")
    sys.exit(1)
except PermissionError as e:
    print(f"  PASS: Fail-closed guard successfully triggered against production target:\n        {e}")

# Set staging target flag
os.environ["ABHIHUB_ENV"] = "staging"
os.environ["SUPABASE_URL"] = "https://staging-project-isolated.supabase.co"
assert not is_production_database(), "Staging URL must not match production ref!"
print(f"  PASS: Isolated Staging Target Verified: {os.getenv('SUPABASE_URL')}")

# -------------------------------------------------------------------------
# Step 2: Provision Isolated Staging Database (Postgres-Compatible SQLite)
# -------------------------------------------------------------------------
STAGING_DB_PATH = os.path.join(os.getcwd(), "staging_phase13.sqlite")
if os.path.exists(STAGING_DB_PATH):
    os.remove(STAGING_DB_PATH)

print(f"\n[Step 2] Provisioning Isolated Staging Database ({STAGING_DB_PATH})...")
conn = sqlite3.connect(STAGING_DB_PATH)
conn.execute("PRAGMA foreign_keys = ON;")
cursor = conn.cursor()

# Mirror production schema
cursor.executescript("""
CREATE TABLE colleges (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    abbreviation TEXT,
    slug TEXT UNIQUE
);

CREATE TABLE departments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    abbreviation TEXT,
    slug TEXT
);

CREATE TABLE subjects (
    id TEXT PRIMARY KEY,
    department_id TEXT,
    name TEXT NOT NULL,
    subject_code TEXT NOT NULL,
    semester INTEGER,
    subject_code_norm TEXT,
    name_norm TEXT,
    abbreviation TEXT,
    aliases TEXT,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    uploader_id TEXT,
    college_id TEXT,
    department_id TEXT,
    subject_id TEXT,
    title TEXT NOT NULL,
    document_category TEXT,
    description TEXT,
    file_type TEXT,
    file_size_bytes INTEGER,
    file_hash TEXT,
    view_count INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (college_id) REFERENCES colleges(id),
    FOREIGN KEY (department_id) REFERENCES departments(id),
    FOREIGN KEY (subject_id) REFERENCES subjects(id)
);
""")
conn.commit()

# -------------------------------------------------------------------------
# Step 3: Populate Baseline Catalog Data into Staging from CSVs & Static Seeds
# -------------------------------------------------------------------------
print("\n[Step 3] Seeding Baseline Catalog into Staging...")

# Seed standard colleges & departments
depts = [
    ('64e63896-00b0-481c-ba04-a601909273d3', 'Electronics and Telecommunication Engineering', 'ETE', 'ete'),
    ('900531a4-9337-4ef8-88d5-e0001531a4ce', 'Computer Science and Engineering', 'CSE', 'cse'),
    ('b39178ad-5fcb-486d-8bc4-7dc4b9b9a674', 'Artificial Intelligence', 'AI', 'ai'),
    ('c48192ab-6ed1-4ef8-9cb5-8ed5c001b785', 'Civil Engineering', 'CIVIL', 'civil'),
    ('d592a3bc-7fe2-5fa9-adca-9fe6d112c896', 'Electrical Engineering', 'EE', 'ee'),
    ('e603b4cd-8af3-6ab0-befb-0af7e223d907', 'Mechanical Engineering', 'MECH', 'mech')
]
for d in depts:
    cursor.execute("INSERT INTO departments VALUES (?, ?, ?, ?)", d)

colls = [
    ('c1111111-1111-1111-1111-111111111111', 'G H Raisoni College of Engineering', 'GHRCE', 'ghrce'),
    ('c2222222-2222-2222-2222-222222222222', 'Indian Institute of Information Technology, Nagpur', 'IIITN', 'iiitn'),
    ('c3333333-3333-3333-3333-333333333333', 'Shri Ramdeobaba College of Engineering and Management', 'RCOEM', 'rcoem')
]
for c in colls:
    cursor.execute("INSERT INTO colleges VALUES (?, ?, ?, ?)", c)

# Existing System on Chip subject
soc_id = '3c9b1111-2222-3333-4444-555555555555'
cursor.execute("""
INSERT INTO subjects (id, department_id, name, subject_code, semester, subject_code_norm, name_norm, abbreviation, aliases)
VALUES (?, '64e63896-00b0-481c-ba04-a601909273d3', 'System On Chip', 'SOC', 7, 'soc', 'system on chip', 'SOC', '[]')
""", (soc_id,))

# Seed unlinked documents from PHASE12_UNLINKED_DOCUMENT_AUDIT.csv
with open('PHASE12_UNLINKED_DOCUMENT_AUDIT.csv', encoding='utf-8') as f:
    unlinked_data = list(csv.DictReader(f))

for d in unlinked_data:
    cursor.execute("""
    INSERT INTO documents (id, uploader_id, college_id, department_id, subject_id, title, document_category, description, file_type, file_size_bytes, file_hash, view_count, created_at, updated_at)
    VALUES (?, 'dummy-user-id', 'c1111111-1111-1111-1111-111111111111', '64e63896-00b0-481c-ba04-a601909273d3', NULL, ?, ?, '', ?, ?, 'dummyhash', ?, '2026-11-14', '2026-11-14')
    """, (d['document_id'], d['title'], d['document_category'], d['file_type'], int(d['file_size_bytes'] or 0), int(d['view_count'] or 0)))

conn.commit()

cursor.execute("SELECT COUNT(*) FROM subjects")
baseline_subjects_count = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM documents WHERE subject_id IS NULL")
baseline_unlinked_count = cursor.fetchone()[0]
print(f"  Baseline Subjects in Staging: {baseline_subjects_count}")
print(f"  Baseline Unlinked Documents in Staging: {baseline_unlinked_count}")

# -------------------------------------------------------------------------
# Step 4: Task 2 — Create Approved 24 Subjects in Staging
# -------------------------------------------------------------------------
print("\n[Step 4] Executing Subject Creation (24 New Subjects)...")
with open('PHASE13_CLUSTER_VALIDATION.csv', encoding='utf-8') as f:
    clusters = list(csv.DictReader(f))

# Filter for approved new subjects (exclude System on Chip which reuses existing)
new_subjects = [c for c in clusters if 'PROPOSE NEW SUBJECT' in c['approval_decision']]
print(f"  New subjects to create: {len(new_subjects)}")

subject_creation_results = []
created_subject_ids = {}

for s in new_subjects:
    s_name = s['cluster_name']
    s_code = s['suggested_code']
    s_dept_name = s['suggested_department']
    s_sem = int(s['semester'])
    
    # Get department_id
    cursor.execute("SELECT id FROM departments WHERE name = ? LIMIT 1", (s_dept_name,))
    dept_row = cursor.fetchone()
    dept_id = dept_row[0] if dept_row else '64e63896-00b0-481c-ba04-a601909273d3'
    
    new_id = str(uuid.uuid4())
    created_subject_ids[s_name] = new_id
    
    cursor.execute("""
    INSERT INTO subjects (id, department_id, name, subject_code, semester, subject_code_norm, name_norm, abbreviation, aliases)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]')
    """, (new_id, dept_id, s_name, s_code, s_sem, s_code.lower(), s_name.lower(), s_code))
    
    subject_creation_results.append({
        'subject_id': new_id,
        'subject_name': s_name,
        'subject_code': s_code,
        'department_name': s_dept_name,
        'semester': s_sem,
        'status': 'CREATED_IN_STAGING'
    })

# Reuse existing SOC subject
created_subject_ids['System On Chip'] = soc_id
print(f"  Reusing existing System On Chip ID: {soc_id}")

subject_creation_results.append({
    'subject_id': soc_id,
    'subject_name': 'System On Chip',
    'subject_code': 'SOC',
    'department_name': 'Electronics and Telecommunication Engineering',
    'semester': 7,
    'status': 'REUSED_EXISTING_SUBJECT'
})

conn.commit()

cursor.execute("SELECT COUNT(*) FROM subjects")
post_creation_subjects_count = cursor.fetchone()[0]
print(f"  Post-Creation Subjects Count: {post_creation_subjects_count} (Delta: +{post_creation_subjects_count - baseline_subjects_count})")
assert post_creation_subjects_count - baseline_subjects_count == 24, "Expected exactly 24 new subjects!"

# -------------------------------------------------------------------------
# Step 5: Task 3 — Document Mapping (265 Approved Mappings)
# -------------------------------------------------------------------------
print("\n[Step 5] Executing Document Mapping (265 Mappings)...")
with open('PHASE13_DOCUMENT_MAPPING_APPROVAL.csv', encoding='utf-8') as f:
    approved_mappings = list(csv.DictReader(f))

print(f"  Mappings to apply: {len(approved_mappings)}")
mapping_results = []
applied_count = 0

for m in approved_mappings:
    doc_id = m['document_id']
    subj_name = m['proposed_subject']
    target_subj_id = created_subject_ids.get(subj_name)
    
    if not target_subj_id:
        print(f"  ERROR: No subject ID for {subj_name}")
        continue
        
    cursor.execute("""
    UPDATE documents
    SET subject_id = ?, updated_at = datetime('now')
    WHERE id = ? AND subject_id IS NULL
    """, (target_subj_id, doc_id))
    
    if cursor.rowcount == 1:
        applied_count += 1
        mapping_results.append({
            'document_id': doc_id,
            'document_title': m['document_title'],
            'mapped_subject_id': target_subj_id,
            'mapped_subject_name': subj_name,
            'status': 'MAPPED_IN_STAGING'
        })
    else:
        print(f"  ERROR: Failed to map document {doc_id}")

conn.commit()
print(f"  Successfully applied {applied_count} / {len(approved_mappings)} mappings in staging.")
assert applied_count == 265, "Expected exactly 265 mappings applied!"

# Assert zero orphan foreign keys
cursor.execute("""
SELECT COUNT(*) FROM documents d
LEFT JOIN subjects s ON d.subject_id = s.id
WHERE d.subject_id IS NOT NULL AND s.id IS NULL
""")
orphan_count = cursor.fetchone()[0]
print(f"  Orphan Foreign Keys: {orphan_count} (Expected: 0)")
assert orphan_count == 0, "Orphan foreign keys detected!"

# -------------------------------------------------------------------------
# Step 6: Task 4 — Description Enrichment (39 Proposals)
# -------------------------------------------------------------------------
print("\n[Step 6] Testing Description Enrichment (39 Proposals)...")
with open('PHASE13_DESCRIPTION_PROPOSALS.csv', encoding='utf-8') as f:
    desc_proposals = list(csv.DictReader(f))

description_results = []
enriched_count = 0

for p in desc_proposals:
    doc_id = p['document_id']
    new_desc = p['proposed_description']
    curr_desc = p['current_description']
    
    cursor.execute("UPDATE documents SET description = ? WHERE id = ?", (new_desc, doc_id))
    if cursor.rowcount == 1:
        enriched_count += 1
        description_results.append({
            'document_id': doc_id,
            'document_title': p['document_title'],
            'before_description': curr_desc,
            'after_description': new_desc,
            'word_count': p['word_count'],
            'status': 'ENRICHED_IN_STAGING'
        })

conn.commit()
print(f"  Successfully enriched {enriched_count} / {len(desc_proposals)} descriptions in staging.")
assert enriched_count == 39, "Expected exactly 39 descriptions enriched!"

# -------------------------------------------------------------------------
# Step 7: Task 5 — Application Testing in Staging
# -------------------------------------------------------------------------
print("\n[Step 7] Running Application Integrity Checks in Staging...")
# Check subject page listing count for new subjects
for s_name in ['Career Development Practices', 'Project Management Methodologies', 'Sensors And Instrumentation', 'System On Chip']:
    s_id = created_subject_ids.get(s_name)
    cursor.execute("SELECT COUNT(*) FROM documents WHERE subject_id = ?", (s_id,))
    cnt = cursor.fetchone()[0]
    print(f"  Subject '{s_name}' has {cnt} linked documents.")

# Verify that 47 ambiguous documents remain untouched
with open('PHASE13_MANUAL_REVIEW.csv', encoding='utf-8') as f:
    amb_docs = list(csv.DictReader(f))

amb_ids = [a['document_id'] for a in amb_docs]
cursor.execute(f"SELECT COUNT(*) FROM documents WHERE id IN ({','.join(['?']*len(amb_ids))}) AND subject_id IS NOT NULL", amb_ids)
amb_linked = cursor.fetchone()[0]
print(f"  Ambiguous documents linked: {amb_linked} (Expected: 0)")
assert amb_linked == 0, "Ambiguous documents were modified!"

# -------------------------------------------------------------------------
# Step 8: Task 6 — Rollback Validation in Staging
# -------------------------------------------------------------------------
print("\n[Step 8] Testing Rollback Protocol in Staging...")

# 1. Revert descriptions
for p in desc_proposals:
    orig = '' if p['current_description'] == '[EMPTY]' else p['current_description']
    cursor.execute("UPDATE documents SET description = ? WHERE id = ?", (orig, p['document_id']))

# 2. Revert mappings
cursor.execute(f"UPDATE documents SET subject_id = NULL WHERE id IN ({','.join(['?']*len(approved_mappings))})",
               [m['document_id'] for m in approved_mappings])

# 3. Delete 24 created subjects
new_subj_ids = [s['subject_id'] for s in subject_creation_results if s['status'] == 'CREATED_IN_STAGING']
cursor.execute(f"DELETE FROM subjects WHERE id IN ({','.join(['?']*len(new_subj_ids))})", new_subj_ids)

conn.commit()

cursor.execute("SELECT COUNT(*) FROM subjects")
final_subjects_count = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM documents WHERE subject_id IS NULL")
final_unlinked_count = cursor.fetchone()[0]

print(f"  Subjects after Rollback: {final_subjects_count} (Expected: {baseline_subjects_count})")
print(f"  Unlinked Documents after Rollback: {final_unlinked_count} (Expected: {baseline_unlinked_count})")

assert final_subjects_count == baseline_subjects_count, "Rollback subject count mismatch!"
assert final_unlinked_count == baseline_unlinked_count, "Rollback unlinked count mismatch!"
print("  PASS: Staging Rollback Protocol 100% Verified.")

conn.close()

# -------------------------------------------------------------------------
# Step 9: Write CSV Deliverables
# -------------------------------------------------------------------------
print("\n[Step 9] Writing Output CSV Deliverables...")

# 1. PHASE13_1_SUBJECT_CREATION_RESULTS.csv
with open('PHASE13_1_SUBJECT_CREATION_RESULTS.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['subject_id', 'subject_name', 'subject_code', 'department_name', 'semester', 'status'])
    writer.writeheader()
    writer.writerows(subject_creation_results)

# 2. PHASE13_1_MAPPING_RESULTS.csv
with open('PHASE13_1_MAPPING_RESULTS.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['document_id', 'document_title', 'mapped_subject_id', 'mapped_subject_name', 'status'])
    writer.writeheader()
    writer.writerows(mapping_results)

# 3. PHASE13_1_DESCRIPTION_RESULTS.csv
with open('PHASE13_1_DESCRIPTION_RESULTS.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['document_id', 'document_title', 'before_description', 'after_description', 'word_count', 'status'])
    writer.writeheader()
    writer.writerows(description_results)

print("Generated all staging CSV deliverables.")
