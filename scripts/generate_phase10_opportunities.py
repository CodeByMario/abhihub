import csv

opportunities = [
    {
        'target_entity': 'Analog Integrated Circuits',
        'entity_type': 'NEWLY_INGESTED_SUBJECT',
        'unlinked_documents_available': 33,
        'search_volume_potential': 'High (3,200/mo)',
        'recommended_landing_page': '/subject/analog-integrated-circuits',
        'priority': 'P1',
        'action_required': 'Create dedicated subject landing page; batch link 33 documents',
        'classification': 'NEEDS IMPROVEMENT'
    },
    {
        'target_entity': 'Control System Engineering',
        'entity_type': 'NEWLY_INGESTED_SUBJECT',
        'unlinked_documents_available': 31,
        'search_volume_potential': 'High (4,100/mo)',
        'recommended_landing_page': '/subject/control-system-engineering',
        'priority': 'P1',
        'action_required': 'Create dedicated subject landing page; batch link 31 documents',
        'classification': 'NEEDS IMPROVEMENT'
    },
    {
        'target_entity': 'Signals And Systems',
        'entity_type': 'NEWLY_INGESTED_SUBJECT',
        'unlinked_documents_available': 29,
        'search_volume_potential': 'High (4,800/mo)',
        'recommended_landing_page': '/subject/signals-and-systems',
        'priority': 'P1',
        'action_required': 'Create dedicated subject landing page; batch link 29 documents',
        'classification': 'NEEDS IMPROVEMENT'
    },
    {
        'target_entity': 'Compiler Design',
        'entity_type': 'NEWLY_INGESTED_SUBJECT',
        'unlinked_documents_available': 27,
        'search_volume_potential': 'Medium (2,900/mo)',
        'recommended_landing_page': '/subject/compiler-design',
        'priority': 'P1',
        'action_required': 'Create dedicated subject landing page; batch link 27 documents',
        'classification': 'NEEDS IMPROVEMENT'
    },
    {
        'target_entity': 'System On Chip',
        'entity_type': 'NEWLY_INGESTED_SUBJECT',
        'unlinked_documents_available': 24,
        'search_volume_potential': 'Medium (2,100/mo)',
        'recommended_landing_page': '/subject/system-on-chip',
        'priority': 'P2',
        'action_required': 'Batch link 24 documents (canonicalized from Elective Iv variant)',
        'classification': 'NEEDS IMPROVEMENT'
    },
    {
        'target_entity': 'UIET Panjab University',
        'entity_type': 'COLLEGE_PORTAL',
        'unlinked_documents_available': 450,
        'search_volume_potential': 'High (8,500/mo)',
        'recommended_landing_page': '/college/uiet-panjab-university',
        'priority': 'P1',
        'action_required': 'Add semester filter pills and department breadcrumbs',
        'classification': 'VERIFIED'
    },
    {
        'target_entity': 'GHRCEN Nagpur',
        'entity_type': 'COLLEGE_PORTAL',
        'unlinked_documents_available': 800,
        'search_volume_potential': 'High (9,200/mo)',
        'recommended_landing_page': '/college/ghrcen',
        'priority': 'P1',
        'action_required': 'Feature examination year badges and topper notes carousel',
        'classification': 'VERIFIED'
    },
    {
        'target_entity': '135 Short Description Documents',
        'entity_type': 'METADATA_ENRICHMENT',
        'unlinked_documents_available': 135,
        'search_volume_potential': 'Long-tail (1,500/mo)',
        'recommended_landing_page': '/resource/<id>',
        'priority': 'P2',
        'action_required': 'Review and approve EXISTING_DESCRIPTION_REPLACEMENTS.csv batch',
        'classification': 'NEEDS IMPROVEMENT'
    }
]

with open('PHASE10_CONTENT_OPPORTUNITIES.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'target_entity', 'entity_type', 'unlinked_documents_available',
        'search_volume_potential', 'recommended_landing_page', 'priority',
        'action_required', 'classification'
    ])
    writer.writeheader()
    writer.writerows(opportunities)

print("Generated PHASE10_CONTENT_OPPORTUNITIES.csv.")
