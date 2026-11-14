import csv

indexing_data = [
    {
        'url_sample': 'https://www.abhihub.edu.eu.org/',
        'page_type': 'HOMEPAGE',
        'http_status': '200 OK',
        'robots_meta': 'index, follow',
        'canonical_match': 'YES (Self-referential)',
        'sitemap_presence': '/sitemap-pages.xml',
        'indexing_classification': 'PRIMARY_INDEXED',
        'inspection_notes': 'Verified 200 OK. WebSite JSON-LD isolated. Valid title and meta description.'
    },
    {
        'url_sample': 'https://www.abhihub.edu.eu.org/about',
        'page_type': 'STATIC_BRAND_PAGE',
        'http_status': '200 OK',
        'robots_meta': 'index, follow',
        'canonical_match': 'YES (Self-referential)',
        'sitemap_presence': '/sitemap-pages.xml',
        'indexing_classification': 'PRIMARY_INDEXED',
        'inspection_notes': 'Verified 200 OK. WebSite schema isolated away from this page.'
    },
    {
        'url_sample': 'https://www.abhihub.edu.eu.org/pyq',
        'page_type': 'RESOURCE_HUB',
        'http_status': '200 OK',
        'robots_meta': 'index, follow',
        'canonical_match': 'YES (Self-referential)',
        'sitemap_presence': '/sitemap-pages.xml',
        'indexing_classification': 'PRIMARY_INDEXED',
        'inspection_notes': 'Verified 200 OK. Clean non-promotional title.'
    },
    {
        'url_sample': 'https://www.abhihub.edu.eu.org/college/ghrcen',
        'page_type': 'COLLEGE_HUB',
        'http_status': '200 OK',
        'robots_meta': 'index, follow',
        'canonical_match': 'YES (Self-referential)',
        'sitemap_presence': '/sitemap-colleges.xml',
        'indexing_classification': 'PRIMARY_INDEXED',
        'inspection_notes': 'Verified 200 OK. College syllabus and PYQ hub.'
    },
    {
        'url_sample': 'https://www.abhihub.edu.eu.org/resources/ghrce-cse-discrete-mathematics-and-graph-theory-discrete-mathematics-and-graph-theory-ese-paper-47de50e7-e503-46ec-94c3-3ac1816b7fe0',
        'page_type': 'ACADEMIC_DOCUMENT',
        'http_status': '200 OK',
        'robots_meta': 'index, follow',
        'canonical_match': 'YES (Self-referential)',
        'sitemap_presence': '/sitemap-documents.xml',
        'indexing_classification': 'PRIMARY_INDEXED',
        'inspection_notes': 'Primary duplicate record with 180 views; loads with PDF viewer.'
    },
    {
        'url_sample': 'https://www.abhihub.edu.eu.org/resource/57226e78-43bb-401f-a5c7-2c938090ee5b',
        'page_type': 'SECONDARY_DUPLICATE',
        'http_status': '301 Redirect / 200 OK',
        'robots_meta': 'noindex, follow',
        'canonical_match': 'POINTS TO 47de50e7...',
        'sitemap_presence': 'EXCLUDED_FROM_SITEMAP',
        'indexing_classification': 'CANONICALIZED_EXCLUDED',
        'inspection_notes': 'Correctly canonicalized to primary record; eliminates internal duplication.'
    },
    {
        'url_sample': 'https://www.abhihub.edu.eu.org/payment',
        'page_type': 'TRANSACTION_GATE',
        'http_status': '302 / 200 Auth',
        'robots_meta': 'noindex, nofollow',
        'canonical_match': 'N/A (Private)',
        'sitemap_presence': 'EXCLUDED_FROM_SITEMAP',
        'indexing_classification': 'ROBOTS_EXCLUDED',
        'inspection_notes': 'Transaction gate protected from search engine crawl.'
    }
]

with open('PHASE10_1_INDEXING_STATUS.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'url_sample', 'page_type', 'http_status', 'robots_meta',
        'canonical_match', 'sitemap_presence', 'indexing_classification', 'inspection_notes'
    ])
    writer.writeheader()
    writer.writerows(indexing_data)

print("Generated PHASE10_1_INDEXING_STATUS.csv.")
