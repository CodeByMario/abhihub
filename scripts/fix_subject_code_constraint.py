import os, sys, csv, re

# Known acronym mappings for all curriculum subjects
ABBR_MAP = {
    'Analog Integrated Circuits': 'AIC',
    'Control System Engineering': 'CSE-ctrl',
    'Signals And Systems': 'SS',
    'Compiler Design': 'CD',
    'Cmos Vlsi Design': 'CVD',
    'Microwave Engineering': 'ME',
    'Deep Learning': 'DL',
    'Numerical Methods And Partial Differential Equations': 'NMPDE',
    'Digital Communication': 'DC',
    'System On Chip': 'SOC',
    'Linear Network Theory': 'LNT',
    'Applications Of Microprocessors And Microcontrollers': 'APMC',
    'Digital Image Processing': 'DIP',
    'Analog Vlsi Design': 'AVD',
    'Applications Of Microprocessor And Microcontroller': 'APMC-1',
    'Concrete Technology': 'CT',
    'Data Warehousing And Etl': 'DWETL',
    'Applications Of Microprocessors And': 'APMC-2',
    'Mobile Game Development': 'MGD',
    'Introduction To Signals And Systems': 'ISS',
    'Cyber Intelligence': 'CI',
    'Field Theory': 'FT',
    'Applications Of Microprocessor Microcontroller': 'APMC-3',
    'Antenna And Wave Propagation': 'AWP',
    'Digital Signal Processing': 'DSP',
    'Optical Communication': 'OC',
    'Web Technology': 'WT',
    'Probability And Statistics': 'PS',
    'Communication Electronics': 'CE',
    'Structural Analysis': 'SA',
    'Pattern Recognition': 'PR',
    'Mathematical Foundation Of Machine Learning': 'MFML',
    'Machining Process': 'MP',
    'Network Theory': 'NT',
    'Introduction To Artificial Intelligence': 'IAI',
    'Numerical Methods And Statistics': 'NMS',
    'Hydraulic Machines': 'HM',
    'Salesforce': 'SF',
    'Elective Cyber Security': 'ECS',
    'Probability Theoryprobability And Statistics': 'PTPS',
    'Basic Control System': 'BCS',
    'Advanced Fluid Mechanics': 'AFM',
    'Material Science And Workshop Practice': 'MSWP',
    'Computer Network Computer Networks': 'CN-2',
    'Introduction To Electronics Devices And': 'IED',
    'Applied Thermodynamics': 'AT',
    'Manufacturing Science And Technology': 'MST',
    'Digital System Design': 'DSD',
    'Transmission Lines And Waveguides': 'TLW',
    'Data Structures': 'DS',
    'Solid State Devices': 'SSD',
    'Fluid Mechanics': 'FM',
    'Kinematics Of Machines': 'KM',
    'Wireless Communication': 'WC',
    'Electrical Machines': 'EM'
}

with open('SUBJECT_PROPOSALS_FINAL.csv', encoding='utf-8') as f:
    props = list(csv.DictReader(f))

for p in props:
    name = p['proposed_name'].strip()
    abbr = ABBR_MAP.get(name)
    if not abbr:
        # Fallback: uppercase initials of words
        abbr = "".join(w[0].upper() for w in re.split(r'\s+', name) if w and w.lower() not in ('and', 'of', 'to', 'for', 'the'))
    p['proposed_abbreviation'] = abbr
    p['subject_code'] = abbr  # Explicit non-null subject_code matching abbreviation

with open('SUBJECT_PROPOSALS_FINAL.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'proposed_name', 'proposed_abbreviation', 'frequency_in_unlinked_docs',
        'suggested_department_id', 'suggested_department', 'subject_code',
        'notes', 'approval_status'
    ])
    writer.writeheader()
    writer.writerows(props)

print(f"Updated SUBJECT_PROPOSALS_FINAL.csv with explicit non-null subject_code values for all {len(props)} subjects.")

# Now re-generate VERIFIED_PRODUCTION_MIGRATION.sql and VERIFIED_PRODUCTION_ROLLBACK.sql
with open('SUBJECT_MAPPINGS_FINAL.csv', encoding='utf-8') as f:
    mappings = list(csv.DictReader(f))
with open('EMPTY_DESCRIPTION_ADDITIONS.csv', encoding='utf-8') as f:
    empty_desc = list(csv.DictReader(f))
with open('DUPLICATE_RESOLUTION_FINAL.csv', encoding='utf-8') as f:
    dups = list(csv.DictReader(f))

mig_lines = []
mig_lines.append("-- =============================================================================")
mig_lines.append("-- ABHIHUB VERIFIED PRODUCTION MIGRATION SCRIPT (CORRECTED NOT-NULL SUBJECT_CODE)")
mig_lines.append("-- TARGET SCHEMA: abhihub (Postgres instance: xchqudjccefnykpuzhxd)")
mig_lines.append("-- STRICT TRANSACTIONAL EXECUTION WITH IDEMPOTENCY GUARDS")
mig_lines.append("-- ZERO DELETION OF DOCUMENTS | ZERO OVERWRITES OF EXISTING DESCRIPTIONS")
mig_lines.append("-- =============================================================================\n")
mig_lines.append("SET search_path = abhihub, public;\n")
mig_lines.append("BEGIN;\n")

# Step 1: Ingest 55 Subjects with explicit non-null subject_code
mig_lines.append("-- -----------------------------------------------------------------------------")
mig_lines.append(f"-- STEP 1: INGEST {len(props)} VERIFIED CURRICULUM SUBJECTS (DEPARTMENT: ETE)")
mig_lines.append("-- Explicit non-null subject_code and abbreviation supplied for every row")
mig_lines.append("-- -----------------------------------------------------------------------------")
for p in props:
    name_esc = p['proposed_name'].replace("'", "''")
    abbr_esc = p['proposed_abbreviation'].replace("'", "''")
    code_esc = p['subject_code'].replace("'", "''")
    dept_id = p['suggested_department_id']
    mig_lines.append(
        f"INSERT INTO abhihub.subjects (department_id, name, subject_code, abbreviation, created_at, updated_at) "
        f"SELECT '{dept_id}', '{name_esc}', '{code_esc}', '{abbr_esc}', NOW(), NOW() "
        f"WHERE NOT EXISTS (SELECT 1 FROM abhihub.subjects WHERE lower(trim(name)) = lower(trim('{name_esc}')) AND department_id = '{dept_id}');"
    )

# Step 2: 17 Mappings
mig_lines.append("\n-- -----------------------------------------------------------------------------")
mig_lines.append(f"-- STEP 2: LINK {len(mappings)} UNLINKED DOCUMENTS TO REGISTERED SUBJECTS")
mig_lines.append("-- -----------------------------------------------------------------------------")
for m in mappings:
    doc_id = m['document_id']
    subj_id = m['proposed_subject_id']
    mig_lines.append(
        f"UPDATE abhihub.documents SET subject_id = '{subj_id}', updated_at = NOW() "
        f"WHERE id = '{doc_id}' AND subject_id IS NULL;"
    )

# Step 3: 129 Empty Descriptions
mig_lines.append("\n-- -----------------------------------------------------------------------------")
mig_lines.append(f"-- STEP 3: POPULATE {len(empty_desc)} EMPTY DESCRIPTIONS (ZERO OVERWRITES)")
mig_lines.append("-- -----------------------------------------------------------------------------")
for ed in empty_desc:
    doc_id = ed['document_id']
    desc_esc = ed['proposed_description'].replace("'", "''")
    mig_lines.append(
        f"UPDATE abhihub.documents SET description = '{desc_esc}', updated_at = NOW() "
        f"WHERE id = '{doc_id}' AND (description IS NULL OR trim(description) = '');"
    )

# Step 4: Duplicate Canonicalization Note
canonical_candidate = dups[3] # DMGT pair
mig_lines.append("\n-- -----------------------------------------------------------------------------")
mig_lines.append("-- STEP 4: DUPLICATE CANONICALIZATION RECORD (ZERO ROW DELETION)")
mig_lines.append(f"-- Primary Document:   {canonical_candidate['primary_document_id']} ({canonical_candidate['primary_title']})")
mig_lines.append(f"-- Secondary Document: {canonical_candidate['secondary_document_id']} ({canonical_candidate['secondary_title']})")
mig_lines.append(f"-- Action: Serve canonical URL pointing to primary and meta robots 'noindex, follow' on secondary.")
mig_lines.append("-- -----------------------------------------------------------------------------")

mig_lines.append("\nCOMMIT;\n")

# Re-generate rollback script
rb_lines = []
rb_lines.append("-- =============================================================================")
rb_lines.append("-- ABHIHUB VERIFIED PRODUCTION ROLLBACK SCRIPT")
rb_lines.append("-- TARGET SCHEMA: abhihub (Postgres instance: xchqudjccefnykpuzhxd)")
rb_lines.append("-- =============================================================================\n")
rb_lines.append("SET search_path = abhihub, public;\n")
rb_lines.append("BEGIN;\n")

names_in = ", ".join(f"'{p['proposed_name'].replace("'", "''")}'" for p in props)
rb_lines.append(f"DELETE FROM abhihub.subjects WHERE department_id = '64e63896-00b0-481c-ba04-a601909273d3' AND name IN ({names_in});\n")

mapped_ids_in = ", ".join(f"'{m['document_id']}'" for m in mappings)
rb_lines.append(f"UPDATE abhihub.documents SET subject_id = NULL, updated_at = NOW() WHERE id IN ({mapped_ids_in});\n")

empty_ids_in = ", ".join(f"'{ed['document_id']}'" for ed in empty_desc)
rb_lines.append(f"UPDATE abhihub.documents SET description = NULL, updated_at = NOW() WHERE id IN ({empty_ids_in});\n")

rb_lines.append("COMMIT;\n")

with open('VERIFIED_PRODUCTION_MIGRATION.sql', 'w', encoding='utf-8') as f:
    f.write("\n".join(mig_lines))

with open('VERIFIED_PRODUCTION_ROLLBACK.sql', 'w', encoding='utf-8') as f:
    f.write("\n".join(rb_lines))

print("Regenerated VERIFIED_PRODUCTION_MIGRATION.sql with explicit subject_code column.")
