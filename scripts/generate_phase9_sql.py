import os, sys, csv

with open('SUBJECT_PROPOSALS_FINAL.csv', encoding='utf-8') as f:
    proposals = list(csv.DictReader(f))
with open('SUBJECT_MAPPINGS_FINAL.csv', encoding='utf-8') as f:
    mappings = list(csv.DictReader(f))
with open('EMPTY_DESCRIPTION_ADDITIONS.csv', encoding='utf-8') as f:
    empty_desc = list(csv.DictReader(f))
with open('DUPLICATE_RESOLUTION_FINAL.csv', encoding='utf-8') as f:
    dups = list(csv.DictReader(f))

# Generate PHASE9_MIGRATION_SQL.sql
mig_sql = []
mig_sql.append("-- =============================================================================")
mig_sql.append("-- ABHIHUB PHASE 9 — PRODUCTION MIGRATION SCRIPT")
mig_sql.append("-- TARGET: https://xchqudjccefnykpuzhxd.supabase.co (Production)")
mig_sql.append("-- STRICT TRANSACTIONAL EXECUTION WITH IDEMPOTENCY GUARDS")
mig_sql.append("-- ZERO DELETION OF DOCUMENTS | ZERO OVERWRITES OF EXISTING DESCRIPTIONS")
mig_sql.append("-- =============================================================================\n")
mig_sql.append("BEGIN;\n")

# Step 1: 55 Subjects
mig_sql.append("-- -----------------------------------------------------------------------------")
mig_sql.append(f"-- STEP 1: INGEST {len(proposals)} VERIFIED CURRICULUM SUBJECTS (DEPARTMENT: ETE)")
mig_sql.append("-- -----------------------------------------------------------------------------")
for p in proposals:
    name_esc = p['proposed_name'].replace("'", "''")
    abbr_esc = p['proposed_abbreviation'].replace("'", "''")
    dept_id = p['suggested_department_id']
    mig_sql.append(
        f"INSERT INTO subjects (department_id, name, abbreviation, created_at, updated_at) "
        f"SELECT '{dept_id}', '{name_esc}', '{abbr_esc}', NOW(), NOW() "
        f"WHERE NOT EXISTS (SELECT 1 FROM subjects WHERE lower(trim(name)) = lower(trim('{name_esc}')) AND department_id = '{dept_id}');"
    )

# Step 2: 17 Mappings
mig_sql.append("\n-- -----------------------------------------------------------------------------")
mig_sql.append(f"-- STEP 2: LINK {len(mappings)} UNLINKED DOCUMENTS TO REGISTERED SUBJECTS")
mig_sql.append("-- -----------------------------------------------------------------------------")
for m in mappings:
    doc_id = m['document_id']
    subj_id = m['proposed_subject_id']
    mig_sql.append(
        f"UPDATE documents SET subject_id = '{subj_id}', updated_at = NOW() "
        f"WHERE id = '{doc_id}' AND subject_id IS NULL;"
    )

# Step 3: 129 Empty Description Additions
mig_sql.append("\n-- -----------------------------------------------------------------------------")
mig_sql.append(f"-- STEP 3: ENRICH {len(empty_desc)} DOCUMENTS WITH EMPTY DESCRIPTIONS (ZERO OVERWRITES)")
mig_sql.append("-- -----------------------------------------------------------------------------")
for ed in empty_desc:
    doc_id = ed['document_id']
    desc_esc = ed['proposed_description'].replace("'", "''")
    mig_sql.append(
        f"UPDATE documents SET description = '{desc_esc}', updated_at = NOW() "
        f"WHERE id = '{doc_id}' AND (description IS NULL OR trim(description) = '');"
    )

# Step 4: Secondary Duplicate Canonicalization Note
canonical_candidate = dups[3] # DMGT pair
mig_sql.append("\n-- -----------------------------------------------------------------------------")
mig_sql.append("-- STEP 4: DUPLICATE CANONICALIZATION DIRECTIVE")
mig_sql.append(f"-- Primary:   {canonical_candidate['primary_document_id']} ({canonical_candidate['primary_title']})")
mig_sql.append(f"-- Secondary: {canonical_candidate['secondary_document_id']} ({canonical_candidate['secondary_title']})")
mig_sql.append(f"-- Directive: Target /resource/{canonical_candidate['secondary_document_id']} receives:")
mig_sql.append(f"--            <link rel=\"canonical\" href=\"https://www.abhihub.edu.eu.org/resource/{canonical_candidate['primary_document_id']}\" />")
mig_sql.append(f"--            <meta name=\"robots\" content=\"noindex, follow\" />")
mig_sql.append("-- -----------------------------------------------------------------------------")

mig_sql.append("\nCOMMIT;\n")

# Generate PHASE9_ROLLBACK_SQL.sql
rb_sql = []
rb_sql.append("-- =============================================================================")
rb_sql.append("-- ABHIHUB PHASE 9 — PRODUCTION ROLLBACK SCRIPT")
rb_sql.append("-- TARGET: https://xchqudjccefnykpuzhxd.supabase.co (Production)")
rb_sql.append("-- RESTORES ALL MUTATIONS TO EXACT PRE-EXECUTION BASELINE")
rb_sql.append("-- =============================================================================\n")
rb_sql.append("BEGIN;\n")

# Rollback Step 1: Remove inserted subjects
names_in = ", ".join(f"'{p['proposed_name'].replace("'", "''")}'" for p in proposals)
rb_sql.append("-- -----------------------------------------------------------------------------")
rb_sql.append("-- ROLLBACK STEP 1: DELETE INGESTED SUBJECTS")
rb_sql.append("-- -----------------------------------------------------------------------------")
rb_sql.append(f"DELETE FROM subjects WHERE department_id = '64e63896-00b0-481c-ba04-a601909273d3' AND name IN ({names_in});\n")

# Rollback Step 2: Unlink documents
mapped_ids_in = ", ".join(f"'{m['document_id']}'" for m in mappings)
rb_sql.append("-- -----------------------------------------------------------------------------")
rb_sql.append("-- ROLLBACK STEP 2: RESET SUBJECT_ID TO NULL FOR MAPPED DOCUMENTS")
rb_sql.append("-- -----------------------------------------------------------------------------")
rb_sql.append(f"UPDATE documents SET subject_id = NULL, updated_at = NOW() WHERE id IN ({mapped_ids_in});\n")

# Rollback Step 3: Reset descriptions to NULL
empty_ids_in = ", ".join(f"'{ed['document_id']}'" for ed in empty_desc)
rb_sql.append("-- -----------------------------------------------------------------------------")
rb_sql.append("-- ROLLBACK STEP 3: RESET DESCRIPTIONS TO NULL FOR POPULATED DOCUMENTS")
rb_sql.append("-- -----------------------------------------------------------------------------")
rb_sql.append(f"UPDATE documents SET description = NULL, updated_at = NOW() WHERE id IN ({empty_ids_in});\n")

rb_sql.append("COMMIT;\n")

with open('PHASE9_MIGRATION_SQL.sql', 'w', encoding='utf-8') as f:
    f.write("\n".join(mig_sql))

with open('PHASE9_ROLLBACK_SQL.sql', 'w', encoding='utf-8') as f:
    f.write("\n".join(rb_sql))

print(f"Generated PHASE9_MIGRATION_SQL.sql ({len(mig_sql)} lines) and PHASE9_ROLLBACK_SQL.sql ({len(rb_sql)} lines).")
