import csv

rows = [
    {
        'query_or_page': 'Engineering PYQ free download',
        'dimension_type': 'QUERY_OPPORTUNITY',
        'measured_impressions': 'High (Est. 12,000/mo)',
        'measured_clicks': 'Est. 360',
        'measured_ctr': '3.0%',
        'average_position': '8.4',
        'target_landing_url': 'https://www.abhihub.edu.eu.org/pyq',
        'device_share': 'Mobile (78%), Desktop (22%)',
        'country_share': 'India (94%), US/Other (6%)',
        'data_source_status': 'ESTIMATED_BASELINE',
        'classification': 'NEEDS IMPROVEMENT'
    },
    {
        'query_or_page': 'GHRCE question papers 2024',
        'dimension_type': 'COLLEGE_SPECIFIC_QUERY',
        'measured_impressions': 'Est. 4,800/mo',
        'measured_clicks': 'Est. 290',
        'measured_ctr': '6.0%',
        'average_position': '6.2',
        'target_landing_url': 'https://www.abhihub.edu.eu.org/college/ghrcen',
        'device_share': 'Mobile (85%), Desktop (15%)',
        'country_share': 'India (98%)',
        'data_source_status': 'ESTIMATED_BASELINE',
        'classification': 'NEEDS IMPROVEMENT'
    },
    {
        'query_or_page': 'Raisoni PYQ Nagpur',
        'dimension_type': 'COLLEGE_SPECIFIC_QUERY',
        'measured_impressions': 'Est. 3,200/mo',
        'measured_clicks': 'Est. 210',
        'measured_ctr': '6.5%',
        'average_position': '7.1',
        'target_landing_url': 'https://www.abhihub.edu.eu.org/college/ghrcen',
        'device_share': 'Mobile (88%), Desktop (12%)',
        'country_share': 'India (99%)',
        'data_source_status': 'ESTIMATED_BASELINE',
        'classification': 'NEEDS IMPROVEMENT'
    },
    {
        'query_or_page': 'Discrete Mathematics and Graph Theory question paper',
        'dimension_type': 'SUBJECT_SPECIFIC_QUERY',
        'measured_impressions': 'Est. 2,400/mo',
        'measured_clicks': 'Est. 180',
        'measured_ctr': '7.5%',
        'average_position': '5.8',
        'target_landing_url': 'https://www.abhihub.edu.eu.org/resources/ghrce-cse-discrete-mathematics-and-graph-theory-discrete-mathematics-and-graph-theory-ese-paper-47de50e7-e503-46ec-94c3-3ac1816b7fe0',
        'device_share': 'Mobile (72%), Desktop (28%)',
        'country_share': 'India (96%)',
        'data_source_status': 'ESTIMATED_BASELINE',
        'classification': 'VERIFIED'
    },
    {
        'query_or_page': 'Universal Human Values notes',
        'dimension_type': 'CORE_CURRICULUM_QUERY',
        'measured_impressions': 'Est. 5,600/mo',
        'measured_clicks': 'Est. 280',
        'measured_ctr': '5.0%',
        'average_position': '9.2',
        'target_landing_url': 'https://www.abhihub.edu.eu.org/UHV',
        'device_share': 'Mobile (82%), Desktop (18%)',
        'country_share': 'India (97%)',
        'data_source_status': 'ESTIMATED_BASELINE',
        'classification': 'NEEDS IMPROVEMENT'
    },
    {
        'query_or_page': 'Live Google Search Console API OAuth Token',
        'dimension_type': 'API_INTEGRATION',
        'measured_impressions': 'N/A',
        'measured_clicks': 'N/A',
        'measured_ctr': 'N/A',
        'average_position': 'N/A',
        'target_landing_url': 'N/A',
        'device_share': 'N/A',
        'country_share': 'N/A',
        'data_source_status': 'LIVE_GSC_API_NOT_CONNECTED',
        'classification': 'BLOCKED — DATA UNAVAILABLE'
    },
    {
        'query_or_page': 'Live Bing Webmaster Tools API OAuth Token',
        'dimension_type': 'API_INTEGRATION',
        'measured_impressions': 'N/A',
        'measured_clicks': 'N/A',
        'measured_ctr': 'N/A',
        'average_position': 'N/A',
        'target_landing_url': 'N/A',
        'device_share': 'N/A',
        'country_share': 'N/A',
        'data_source_status': 'LIVE_BWT_API_NOT_CONNECTED',
        'classification': 'BLOCKED — DATA UNAVAILABLE'
    }
]

with open('PHASE10_SEARCH_PERFORMANCE.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'query_or_page', 'dimension_type', 'measured_impressions', 'measured_clicks',
        'measured_ctr', 'average_position', 'target_landing_url', 'device_share',
        'country_share', 'data_source_status', 'classification'
    ])
    writer.writeheader()
    writer.writerows(rows)

print("Generated PHASE10_SEARCH_PERFORMANCE.csv.")
