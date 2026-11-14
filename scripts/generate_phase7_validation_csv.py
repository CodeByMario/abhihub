import os, sys, csv

sys.path.insert(0, os.getcwd())
from methods.supabase_helper import init_supabase, init_supabase_admin

client = init_supabase_admin() or init_supabase()

print("Compiling Phase 7 Database Validation Baseline...")

# Record current baseline counts directly from DB
total_docs = client.table('documents').select('id', count='exact').execute().count
unlinked_docs = client.table('documents').select('id', count='exact').is_('subject_id', 'null').execute().count
total_subjects = client.table('subjects').select('id', count='exact').execute().count
total_colleges = client.table('colleges').select('id', count='exact').execute().count
total_departments = client.table('departments').select('id', count='exact').execute().count

# Staged targets from final Phase 6.2 CSVs
with open('SUBJECT_PROPOSALS_FINAL.csv', encoding='utf-8') as f:
    staged_subjects = len(list(csv.DictReader(f)))
with open('SUBJECT_MAPPINGS_FINAL.csv', encoding='utf-8') as f:
    staged_mappings = len(list(csv.DictReader(f)))
with open('EMPTY_DESCRIPTION_ADDITIONS.csv', encoding='utf-8') as f:
    staged_empty_desc = len(list(csv.DictReader(f)))
with open('EXISTING_DESCRIPTION_REPLACEMENTS.csv', encoding='utf-8') as f:
    staged_replacements = len(list(csv.DictReader(f)))
with open('DUPLICATE_RESOLUTION_FINAL.csv', encoding='utf-8') as f:
    staged_duplicates = len(list(csv.DictReader(f)))

validation_rows = [
    {
        'metric_category': 'DATABASE_BASELINE',
        'metric_name': 'total_documents',
        'current_database_value': total_docs,
        'staged_target_change': '0',
        'post_execution_expected': total_docs,
        'status': 'VERIFIED_BASELINE',
        'audit_notes': 'Total document rows across all colleges and departments'
    },
    {
        'metric_category': 'DATABASE_BASELINE',
        'metric_name': 'unlinked_documents',
        'current_database_value': unlinked_docs,
        'staged_target_change': f"-{staged_mappings}",
        'post_execution_expected': unlinked_docs - staged_mappings,
        'status': 'STAGED_READY',
        'audit_notes': f"Documents with subject_id null; {staged_mappings} Tier-2 mappings staged"
    },
    {
        'metric_category': 'DATABASE_BASELINE',
        'metric_name': 'total_subjects',
        'current_database_value': total_subjects,
        'staged_target_change': f"+{staged_subjects}",
        'post_execution_expected': total_subjects + staged_subjects,
        'status': 'STAGED_READY',
        'audit_notes': f"Catalog size; {staged_subjects} validated ETE subjects staged"
    },
    {
        'metric_category': 'DATABASE_BASELINE',
        'metric_name': 'total_colleges',
        'current_database_value': total_colleges,
        'staged_target_change': '0',
        'post_execution_expected': total_colleges,
        'status': 'VERIFIED_BASELINE',
        'audit_notes': 'Colleges catalog is preserved with zero changes'
    },
    {
        'metric_category': 'DATABASE_BASELINE',
        'metric_name': 'total_departments',
        'current_database_value': total_departments,
        'staged_target_change': '0',
        'post_execution_expected': total_departments,
        'status': 'VERIFIED_BASELINE',
        'audit_notes': 'Departments catalog is preserved with zero changes'
    },
    {
        'metric_category': 'STAGED_OPERATION',
        'metric_name': 'subject_insertions',
        'current_database_value': 0,
        'staged_target_change': staged_subjects,
        'post_execution_expected': staged_subjects,
        'status': 'STAGED_READY',
        'audit_notes': '55 unique curriculum subjects ready in FINAL_STAGING_SQL.sql Stage 1'
    },
    {
        'metric_category': 'STAGED_OPERATION',
        'metric_name': 'document_subject_mappings',
        'current_database_value': 0,
        'staged_target_change': staged_mappings,
        'post_execution_expected': staged_mappings,
        'status': 'STAGED_READY',
        'audit_notes': '17 validated document-to-subject links ready in FINAL_STAGING_SQL.sql Stage 2'
    },
    {
        'metric_category': 'STAGED_OPERATION',
        'metric_name': 'empty_description_additions',
        'current_database_value': 0,
        'staged_target_change': staged_empty_desc,
        'post_execution_expected': staged_empty_desc,
        'status': 'STAGED_READY',
        'audit_notes': '129 empty descriptions ready in FINAL_STAGING_SQL.sql Stage 3 (zero overwrites)'
    },
    {
        'metric_category': 'STAGED_OPERATION',
        'metric_name': 'existing_description_replacements',
        'current_database_value': 0,
        'staged_target_change': '0 (HELD)',
        'post_execution_expected': '0 (HELD)',
        'status': 'EXCLUDED_PENDING_CONFIRMATION',
        'audit_notes': f"{staged_replacements} short description replacements held; commented out in SQL"
    },
    {
        'metric_category': 'STAGED_OPERATION',
        'metric_name': 'duplicate_canonicalizations',
        'current_database_value': 0,
        'staged_target_change': '1 (secondary noindex)',
        'post_execution_expected': '1 (secondary noindex)',
        'status': 'STAGED_READY',
        'audit_notes': 'Pair 1 (DMGT) safe canonicalization; 2 preserve cases and 1 unsafe review case kept independent'
    },
    {
        'metric_category': 'SAFETY_GATE',
        'metric_name': 'environment_identification',
        'current_database_value': 'PRODUCTION_SHARED',
        'staged_target_change': '0',
        'post_execution_expected': 'N/A',
        'status': 'HALTED_FOR_SAFETY',
        'audit_notes': 'Active DB is production xchqudjccefnykpuzhxd; staging instance not configured in .env'
    }
]

with open('PHASE7_DATABASE_VALIDATION.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'metric_category', 'metric_name', 'current_database_value',
        'staged_target_change', 'post_execution_expected', 'status', 'audit_notes'
    ])
    writer.writeheader()
    writer.writerows(validation_rows)

print(f"Generated PHASE7_DATABASE_VALIDATION.csv with {len(validation_rows)} baseline and staged metrics.")
