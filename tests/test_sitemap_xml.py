import xml.etree.ElementTree as ET
import pytest
from routes.seo import _build_sitemap_index_xml, _build_urlset_xml


def test_build_sitemap_index_xml_structure():
    sitemaps = [
        {'loc': 'https://www.abhihub.edu.eu.org/sitemap-pages.xml', 'lastmod': '2026-10-20'},
        {'loc': 'https://www.abhihub.edu.eu.org/sitemap-colleges.xml', 'lastmod': '2026-10-20'},
        {'loc': 'https://www.abhihub.edu.eu.org/sitemap-documents.xml', 'lastmod': '2026-10-20'},
    ]
    xml_bytes = _build_sitemap_index_xml(sitemaps)
    assert xml_bytes.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')

    # Must parse cleanly without syntax or nesting errors
    root = ET.fromstring(xml_bytes.replace(b'<?xml version="1.0" encoding="UTF-8"?>', b'').strip())
    assert root.tag.endswith('sitemapindex')
    assert len(root) == 3

    for child in root:
        assert child.tag.endswith('sitemap')
        # Ensure no nested <sitemap> inside <sitemap>
        assert len(child.findall('{*}sitemap')) == 0
        loc_nodes = child.findall('{*}loc')
        assert len(loc_nodes) == 1
        # Ensure no nested <loc> inside <loc>
        assert len(loc_nodes[0].findall('{*}loc')) == 0
        lastmod_nodes = child.findall('{*}lastmod')
        assert len(lastmod_nodes) == 1
        assert len(lastmod_nodes[0].findall('{*}lastmod')) == 0


def test_build_urlset_xml_structure():
    urls = [
        {'loc': 'https://www.abhihub.edu.eu.org/about', 'priority': '0.80', 'changefreq': 'weekly'},
        {'loc': 'https://www.abhihub.edu.eu.org/contact', 'lastmod': '2026-10-20', 'priority': '0.70', 'changefreq': 'monthly'}
    ]
    xml_bytes = _build_urlset_xml(urls)
    assert xml_bytes.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')

    # Must parse cleanly
    root = ET.fromstring(xml_bytes.replace(b'<?xml version="1.0" encoding="UTF-8"?>', b'').strip())
    assert root.tag.endswith('urlset')
    assert len(root) == 2

    for child in root:
        assert child.tag.endswith('url')
        assert len(child.findall('{*}url')) == 0
        loc_nodes = child.findall('{*}loc')
        assert len(loc_nodes) == 1
        assert len(loc_nodes[0].findall('{*}loc')) == 0
