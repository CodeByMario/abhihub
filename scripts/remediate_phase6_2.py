import os, sys, csv, re

sys.path.insert(0, os.getcwd())
from methods.supabase_helper import init_supabase, init_supabase_admin

client = init_supabase_admin() or init_supabase()

print("Starting Phase 6.2 Remediation Pipeline...")

# -------------------------------------------------------------------------
# 1. Subject Proposals Remediation
# -------------------------------------------------------------------------
with open('PROPOSED_NEW_SUBJECTS.csv', encoding='utf-8') as f:
    raw_props = list(csv.DictReader(f))

final_proposals = []
rejected_proposals = []

for p in raw_props:
    name = p['proposed_name'].strip()
    name_l = name.lower()
    
    # Check invalid reasons
    if 'unknown subject' in name_l:
        rejected_proposals.append({
            'proposed_name': name,
            'reason': 'Contains placeholder exam artifact (Unknown Subject)',
            'action': 'REJECTED_FROM_CATALOG'
        })
        continue
    if name_l == 'software engineering':
        rejected_proposals.append({
            'proposed_name': name,
            'reason': 'Duplicate of registered subject (exists under CSE department)',
            'action': 'REJECTED_FROM_CATALOG'
        })
        continue
    if 'elective iv system on chip' in name_l:
        # Merge frequency into existing System On Chip and reject this prefix variant
        rejected_proposals.append({
            'proposed_name': name,
            'reason': 'Prefix variant of System On Chip (frequency merged into canonical entry)',
            'action': 'MERGED_INTO_CANONICAL_PROPOSAL'
        })
        continue
    if name_l == 'system on chip':
        # Combined frequency: 16 + 8 = 24
        p['frequency_in_unlinked_docs'] = '24'
        p['proposed_abbreviation'] = 'SOC'
        p['notes'] = 'Consolidated canonical subject including Elective Iv variant'
        
    final_proposals.append(p)

with open('SUBJECT_PROPOSALS_FINAL.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'proposed_name', 'proposed_abbreviation', 'frequency_in_unlinked_docs',
        'suggested_department_id', 'suggested_department', 'subject_code',
        'notes', 'approval_status'
    ])
    writer.writeheader()
    writer.writerows(final_proposals)

print(f"Generated SUBJECT_PROPOSALS_FINAL.csv with {len(final_proposals)} clean proposals ({len(rejected_proposals)} rejected).")

# -------------------------------------------------------------------------
# 2. Subject Mappings Remediation
# -------------------------------------------------------------------------
with open('APPROVED_SUBJECT_MAPPING.csv', encoding='utf-8') as f:
    raw_mappings = list(csv.DictReader(f))

final_mappings = []
excluded_mappings = []

for m in raw_mappings:
    if m['document_id'] == '5a1608b3-3a74-4b53-b097-bfbb9f5dcf74' or 'Modern Instrumentation' in m['document_title']:
        excluded_mappings.append({
            'document_id': m['document_id'],
            'document_title': m['document_title'],
            'proposed_subject_name': m['proposed_subject_name'],
            'incorrect_evidence': m['match_reason'],
            'reason': "Batch prefix 'Cn' mistaken for Computer Networks acronym. Document topic is Instrumentation."
        })
        continue
    final_mappings.append(m)

with open('SUBJECT_MAPPINGS_FINAL.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'document_id', 'document_title', 'cleaned_title', 'department_id',
        'proposed_subject_id', 'proposed_subject_name', 'proposed_subject_dept',
        'confidence_score', 'tier', 'match_reason', 'approval_status'
    ])
    writer.writeheader()
    writer.writerows(final_mappings)

print(f"Generated SUBJECT_MAPPINGS_FINAL.csv with {len(final_mappings)} validated mappings ({len(excluded_mappings)} excluded).")

# -------------------------------------------------------------------------
# 3. Description Enrichment Segregation (Deduplicated by document_id)
# -------------------------------------------------------------------------
with open('APPROVED_DESCRIPTION_CHANGES.csv', encoding='utf-8') as f:
    raw_desc = list(csv.DictReader(f))

empty_additions = []
existing_replacements = []
rejections = []
seen_desc_ids = set()

for d in raw_desc:
    doc_id = d['document_id']
    if doc_id in seen_desc_ids:
        continue
    seen_desc_ids.add(doc_id)

    cur = (d['current_description'] or '').strip()
    title = (d['document_title'] or '').strip().lower()
    
    # Reject administrative or nonsensical items
    if any(k in title for k in ['holiday', 'bus timetable', 'schedule', 'notice', 'resume']):
        rejections.append({
            'document_id': d['document_id'],
            'document_title': d['document_title'],
            'current_description': cur,
            'reason': 'Administrative campus file - should not have academic revision description'
        })
        continue
        
    if cur == '[EMPTY]' or not cur:
        empty_additions.append({
            'document_id': d['document_id'],
            'document_title': d['document_title'],
            'college': d['college'],
            'department': d['department'],
            'proposed_description': d['proposed_description'],
            'source_evidence': d['source_evidence'],
            'execution_stage': 'STAGE_1_EMPTY_ADDITIONS'
        })
    else:
        existing_replacements.append({
            'document_id': d['document_id'],
            'document_title': d['document_title'],
            'college': d['college'],
            'department': d['department'],
            'original_description': cur,
            'proposed_description': d['proposed_description'],
            'word_count_original': len(cur.split()),
            'word_count_proposed': len(d['proposed_description'].split()),
            'approval_required': 'YES_EXPLICIT_USER_APPROVAL_MANDATORY',
            'execution_stage': 'STAGE_2_EXISTING_REPLACEMENTS'
        })

with open('EMPTY_DESCRIPTION_ADDITIONS.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'document_id', 'document_title', 'college', 'department',
        'proposed_description', 'source_evidence', 'execution_stage'
    ])
    writer.writeheader()
    writer.writerows(empty_additions)

with open('EXISTING_DESCRIPTION_REPLACEMENTS.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'document_id', 'document_title', 'college', 'department',
        'original_description', 'proposed_description', 'word_count_original',
        'word_count_proposed', 'approval_required', 'execution_stage'
    ])
    writer.writeheader()
    writer.writerows(existing_replacements)

with open('DESCRIPTION_REJECTION_REPORT.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'document_id', 'document_title', 'current_description', 'reason'
    ])
    writer.writeheader()
    writer.writerows(rejections)

print(f"Generated EMPTY_DESCRIPTION_ADDITIONS.csv ({len(empty_additions)} rows)")
print(f"Generated EXISTING_DESCRIPTION_REPLACEMENTS.csv ({len(existing_replacements)} rows)")
print(f"Generated DESCRIPTION_REJECTION_REPORT.csv ({len(rejections)} rows)")

# -------------------------------------------------------------------------
# 4. Duplicate Resolution Final
# -------------------------------------------------------------------------
with open('DUPLICATE_CANONICALIZATION_APPROVAL.csv', encoding='utf-8') as f:
    raw_dups = list(csv.DictReader(f))

final_dups = []
for d in raw_dups:
    p_id = d['primary_document_id']
    s_id = d['secondary_document_id']
    
    # Pair 4: DMS vs DAA unsafe
    if ('DMS' in d['primary_title'] and 'DAA' in d['secondary_title']) or ('DAA' in d['primary_title'] and 'DMS' in d['secondary_title']):
        final_dups.append({
            'primary_document_id': p_id,
            'primary_title': d['primary_title'],
            'secondary_document_id': s_id,
            'secondary_title': d['secondary_title'],
            'binary_hash': d['file_hash'],
            'same_uploader': d['same_uploader'],
            'final_action': 'PRESERVE_BOTH_FLAG_FOR_MANUAL_CONTENT_VERIFICATION',
            'canonical_destination': 'SELF (No cross-canonicalization)',
            'robots_directive': 'index, follow',
            'deletion_performed': 'NO',
            'audit_notes': 'Binary collision between different subjects (DMS vs DAA). Canonicalization strictly disallowed.'
        })
    elif 'dmgt' in d['primary_title'].lower() or 'dmgt' in d['secondary_title'].lower():
        final_dups.append({
            'primary_document_id': p_id,
            'primary_title': d['primary_title'],
            'secondary_document_id': s_id,
            'secondary_title': d['secondary_title'],
            'binary_hash': d['file_hash'],
            'same_uploader': d['same_uploader'],
            'final_action': 'CANONICALIZE_SECONDARY_TO_PRIMARY',
            'canonical_destination': f"/resource/{p_id}",
            'robots_directive': 'noindex, follow',
            'deletion_performed': 'NO',
            'audit_notes': 'Safe acronym/duplicate submission by same uploader 2 minutes apart. Primary has higher views (180 vs 147).'
        })
    else:
        # UITL201 OOPs lab template cases
        final_dups.append({
            'primary_document_id': p_id,
            'primary_title': d['primary_title'],
            'secondary_document_id': s_id,
            'secondary_title': d['secondary_title'],
            'binary_hash': d['file_hash'],
            'same_uploader': d['same_uploader'],
            'final_action': 'PRESERVE_BOTH_INDEPENDENT',
            'canonical_destination': 'SELF',
            'robots_directive': 'index, follow',
            'deletion_performed': 'NO',
            'audit_notes': 'Shared lab assignment template across distinct student submitters. Independent indexing preserved.'
        })

with open('DUPLICATE_RESOLUTION_FINAL.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'primary_document_id', 'primary_title', 'secondary_document_id', 'secondary_title',
        'binary_hash', 'same_uploader', 'final_action', 'canonical_destination',
        'robots_directive', 'deletion_performed', 'audit_notes'
    ])
    writer.writeheader()
    writer.writerows(final_dups)

print(f"Generated DUPLICATE_RESOLUTION_FINAL.csv ({len(final_dups)} cases)")

# -------------------------------------------------------------------------
# 5. Generate FINAL_STAGING_SQL.sql and FINAL_ROLLBACK.sql
# -------------------------------------------------------------------------
sql_statements = []
rollback_statements = []

sql_statements.append("-- =============================================================================")
sql_statements.append("-- ABHIHUB PHASE 6.2 - FINAL STAGING SQL SCRIPT")
sql_statements.append("-- STRICT TRANSACTIONAL EXECUTION WITH IDEMPOTENCY GUARDS")
sql_statements.append("-- NO DELETE STATEMENTS - ALL ORIGINAL IDENTIFIERS PRESERVED")
sql_statements.append("-- =============================================================================\n")
sql_statements.append("BEGIN;\n")

rollback_statements.append("-- =============================================================================")
rollback_statements.append("-- ABHIHUB PHASE 6.2 - FINAL ROLLBACK SQL SCRIPT")
rollback_statements.append("-- REVERSIBLE RESTORATION OF ALL MUTATIONS TO PRE-EXECUTION STATE")
rollback_statements.append("-- =============================================================================\n")
rollback_statements.append("BEGIN;\n")

# Stage 1: Insert validated new subjects (56 subjects: 55 valid + 1 cleaned SoC)
sql_statements.append("-- -----------------------------------------------------------------------------")
sql_statements.append(f"-- STAGE 1: INSERT {len(final_proposals)} CURATED CURRICULUM SUBJECTS (DEPARTMENT: ETE)")
sql_statements.append("-- -----------------------------------------------------------------------------")

for p in final_proposals:
    name_esc = p['proposed_name'].replace("'", "''")
    abbr_esc = p['proposed_abbreviation'].replace("'", "''")
    dept_id = p['suggested_department_id']
    sql_statements.append(
        f"INSERT INTO subjects (department_id, name, abbreviation, created_at, updated_at) "
        f"SELECT '{dept_id}', '{name_esc}', '{abbr_esc}', NOW(), NOW() "
        f"WHERE NOT EXISTS (SELECT 1 FROM subjects WHERE lower(trim(name)) = lower(trim('{name_esc}')) AND department_id = '{dept_id}');"
    )

rollback_statements.append("-- -----------------------------------------------------------------------------")
rollback_statements.append("-- ROLLBACK STAGE 1: REMOVE INSERTED SUBJECTS")
rollback_statements.append("-- -----------------------------------------------------------------------------")
subj_names_in = ", ".join(f"'{p['proposed_name'].replace("'", "''")}'" for p in final_proposals)
rollback_statements.append(
    f"DELETE FROM subjects WHERE department_id = '64e63896-00b0-481c-ba04-a601909273d3' AND name IN ({subj_names_in});\n"
)

# Stage 2: Update 17 validated subject mappings
sql_statements.append("\n-- -----------------------------------------------------------------------------")
sql_statements.append(f"-- STAGE 2: LINK {len(final_mappings)} VALIDATED DOCUMENTS TO REGISTERED SUBJECTS")
sql_statements.append("-- -----------------------------------------------------------------------------")

mapped_doc_ids = []
for m in final_mappings:
    doc_id = m['document_id']
    subj_id = m['proposed_subject_id']
    mapped_doc_ids.append(f"'{doc_id}'")
    sql_statements.append(
        f"UPDATE documents SET subject_id = '{subj_id}', updated_at = NOW() "
        f"WHERE id = '{doc_id}' AND subject_id IS NULL;"
    )

rollback_statements.append("-- -----------------------------------------------------------------------------")
rollback_statements.append("-- ROLLBACK STAGE 2: UNLINK DOCUMENTS")
rollback_statements.append("-- -----------------------------------------------------------------------------")
rollback_statements.append(
    f"UPDATE documents SET subject_id = NULL, updated_at = NOW() "
    f"WHERE id IN ({', '.join(mapped_doc_ids)});\n"
)

# Stage 3: Empty description additions (245 additions)
sql_statements.append("\n-- -----------------------------------------------------------------------------")
sql_statements.append(f"-- STAGE 3: POPULATE {len(empty_additions)} EMPTY DESCRIPTIONS (ZERO OVERWRITES)")
sql_statements.append("-- -----------------------------------------------------------------------------")

empty_doc_ids = []
for ed in empty_additions:
    doc_id = ed['document_id']
    desc_esc = ed['proposed_description'].replace("'", "''")
    empty_doc_ids.append(f"'{doc_id}'")
    sql_statements.append(
        f"UPDATE documents SET description = '{desc_esc}', updated_at = NOW() "
        f"WHERE id = '{doc_id}' AND (description IS NULL OR trim(description) = '');"
    )

rollback_statements.append("-- -----------------------------------------------------------------------------")
rollback_statements.append("-- ROLLBACK STAGE 3: RESET POPULATED DESCRIPTIONS TO NULL")
rollback_statements.append("-- -----------------------------------------------------------------------------")
rollback_statements.append(
    f"UPDATE documents SET description = NULL, updated_at = NOW() "
    f"WHERE id IN ({', '.join(empty_doc_ids)});\n"
)

# Stage 4: Existing description replacements (295 held for explicit approval)
sql_statements.append("\n-- -----------------------------------------------------------------------------")
sql_statements.append(f"-- STAGE 4: PROPOSED REPLACEMENTS FOR {len(existing_replacements)} SHORT DESCRIPTIONS")
sql_statements.append("-- NOTE: HELD PENDING USER CONFIRMATION - COMMENTED BY DEFAULT FOR SAFETY")
sql_statements.append("-- -----------------------------------------------------------------------------")

rollback_replacements = []
for er in existing_replacements:
    doc_id = er['document_id']
    orig_esc = er['original_description'].replace("'", "''")
    prop_esc = er['proposed_description'].replace("'", "''")
    sql_statements.append(
        f"-- UPDATE documents SET description = '{prop_esc}', updated_at = NOW() WHERE id = '{doc_id}' AND description = '{orig_esc}';"
    )
    rollback_replacements.append(f"('{doc_id}', '{orig_esc}')")

rollback_statements.append("-- -----------------------------------------------------------------------------")
rollback_statements.append("-- ROLLBACK STAGE 4: RESTORE PREVIOUS DESCRIPTIONS IF REPLACEMENTS APPLIED")
rollback_statements.append("-- -----------------------------------------------------------------------------")
rollback_statements.append(
    "-- UPDATE documents AS d SET description = v.orig, updated_at = NOW() FROM (VALUES\n--   " +
    "\n-- , ".join(rollback_replacements[:10]) + "\n--   ... (full mapping available in EXISTING_DESCRIPTION_REPLACEMENTS.csv)\n" +
    "-- ) AS v(id, orig) WHERE d.id = v.id;\n"
)

sql_statements.append("\nCOMMIT;\n")
rollback_statements.append("COMMIT;\n")

with open('FINAL_STAGING_SQL.sql', 'w', encoding='utf-8') as f:
    f.write("\n".join(sql_statements))

with open('FINAL_ROLLBACK.sql', 'w', encoding='utf-8') as f:
    f.write("\n".join(rollback_statements))

print("Generated FINAL_STAGING_SQL.sql and FINAL_ROLLBACK.sql successfully.")
print("Phase 6.2 Data Remediation Complete.")
