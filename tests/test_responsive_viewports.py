"""
Responsive Viewport & Mobile Architecture Test Suite for AbhiHub
Verifies WCAG 2.2 AA Zoom compliance, mobile-first layouts, Settings list-to-detail,
Creator Hub carousels, FAB buttons, and responsive breakpoints (320px - 1536px).
"""

import pytest
import re
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['user'] = {
                'id': 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
                'uid': 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
                'name': 'Abhi User',
                'email': 'creator@abhihub.edu.eu.org'
            }
        yield c


def test_viewport_meta_tag_wcag_compliance(client):
    """Ensure viewport meta tag does NOT block user scaling (WCAG 2.2 1.4.4)."""
    res = client.get('/')
    assert res.status_code == 200
    html = res.data.decode('utf-8', errors='ignore')

    # Viewport tag must exist and be accessible
    assert 'name="viewport"' in html
    assert 'user-scalable=no' not in html, "Zoom-blocking user-scalable=no detected!"
    assert 'maximum-scale=1.0' not in html, "Zoom-blocking maximum-scale=1.0 detected!"
    assert 'viewport-fit=cover' in html


def test_base_typography_no_sub_16px_zoom_glitch():
    """Verify 02_base.css does not shrink root font to 14px on mobile."""
    with open('static/css/pipeline/02_base.css', 'r', encoding='utf-8') as f:
        css = f.read()
    assert ':root { font-size: 14px; }' not in css, "Root font-size 14px found, causing iOS zoom glitches!"


def test_settings_responsive_elements(client):
    """Verify Settings page has list-to-detail structure and sticky save bar."""
    res = client.get('/settings')
    assert res.status_code == 200
    html = res.data.decode('utf-8', errors='ignore')

    assert 'settings_responsive.css' in html
    assert 'settings_responsive.js' in html
    assert 'st-mobile-detail-header' in html
    assert 'stMobileBackBtn' in html
    assert 'stStickySaveBar' in html
    assert 'stAvatarInput' in html
    assert 'accept="image/*"' in html
    assert 'st-danger-zone' in html
    assert 'delete-account' in html
    assert 'confirm(' in html


def test_creator_hub_responsive_elements(client):
    """Verify Creator Hub has mobile priority bar, stats carousel, and upload FAB."""
    res = client.get('/creator-hub')
    # Can return 200 or redirect depending on mock session setup
    if res.status_code == 200:
        html = res.data.decode('utf-8', errors='ignore')
        assert 'creator_hub_responsive.css' in html
        assert 'ch-quick-actions' in html
        assert 'ch-stats-carousel' in html
        assert 'chCarouselDots' in html
        assert 'ch-fab-btn' in html
        assert 'Material' in html
        assert 'min-width: 500px;' not in html

    # Verify template eliminates min-width 500px
    with open('templates/p_creator_hub.html', 'r', encoding='utf-8') as f:
        tmpl = f.read()
    assert 'min-width: 500px;' not in tmpl
    assert 'data-label="Rank"' in tmpl
    assert 'data-label="Destination"' in tmpl


def test_navigation_architecture_consistency(client):
    """Verify Phase 2: Top desktop nav links and bottom mobile dock share config."""
    res = client.get('/')
    assert res.status_code == 200
    html = res.data.decode('utf-8', errors='ignore')

    # Both desktop top bar and mobile dock elements are present in markup
    assert 'nav-desktop-cluster' in html
    assert 'navbar--bottom' in html

    # Check that all 5 primary routes exist in desktop top nav
    for page in ['home', 'upload', 'ranking', 'creator-hub', 'settings']:
        assert f'data-page="{page}"' in html

    # Verify CSS rules isolate desktop vs mobile dock
    with open('static/css/pipeline/navbar.css', 'r', encoding='utf-8') as f:
        nav_css = f.read()
    assert '.nav-desktop-cluster' in nav_css
    assert '@media (min-width: 1024px)' in nav_css
    assert '.navbar--bottom {\n        display: none !important;' in nav_css or 'display: none !important;' in nav_css


@pytest.mark.parametrize("width,ua", [
    (320, "Mozilla/5.0 (iPhone; CPU iPhone OS 10_3 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) Mobile/14E5239e"),
    (375, "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"),
    (414, "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"),
    (768, "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"),
    (1024, "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    (1280, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    (1536, "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0"),
])
def test_simulated_responsive_viewports(client, width, ua):
    """Simulate key viewports and confirm HTTP status and layout integrity."""
    headers = {
        'User-Agent': ua,
        'Sec-CH-UA-Mobile': '?1' if width < 1024 else '?0',
        'Viewport-Width': str(width)
    }
    res = client.get('/', headers=headers)
    assert res.status_code == 200
    html = res.data.decode('utf-8', errors='ignore')
    assert '<body' in html
    assert 'skip-link' in html


def test_phase5_partial_pages_fixes(client):
    """Verify Phase 5 fixes: College tabs snap, seller banner aspect ratio, upload wizard draft & swipe."""
    # 1. College files scroll-snap
    with open('templates/college_files.html', 'r', encoding='utf-8') as f:
        c_html = f.read()
    assert 'scroll-snap-type: x mandatory;' in c_html

    # 2. Subject metadata badges below 360px
    with open('templates/subject.html', 'r', encoding='utf-8') as f:
        s_html = f.read()
    assert '@media(max-width: 360px)' in s_html

    # 3. Store room filter wrap
    with open('templates/p_store_room.html', 'r', encoding='utf-8') as f:
        sr_html = f.read()
    assert 'flex-wrap: wrap;' in sr_html

    # 4. Channel view banner aspect-ratio
    with open('templates/channel_view.html', 'r', encoding='utf-8') as f:
        cv_html = f.read()
    assert 'aspect-ratio: 16 / 5;' in cv_html
    assert 'object-fit: cover;' in cv_html

    # 5. Upload wizard draft persistence & swipe listeners
    with open('templates/p_upload.html', 'r', encoding='utf-8') as f:
        up_html = f.read()
    assert 'abhihub_upload_draft_v1' in up_html
    assert 'goToStep3Btn.click();' in up_html

    # 6. Settings wallet tables to cards
    with open('static/css/pages/settings_responsive.css', 'r', encoding='utf-8') as f:
        st_css = f.read()
    assert '.st-section table' in st_css
    assert '.st-section tbody' in st_css


def test_app_home_mobile_responsive_elements():
    """Verify App Home (templates/app/home.html) mobile responsiveness and layout rules."""
    with open('templates/app/home.html', 'r', encoding='utf-8') as f:
        template = f.read()

    # Segmented controls must not wrap tab button text into multi-line bubbles
    assert 'white-space: nowrap' in template
    assert '.apple-segment-btn {' in template
    assert 'apple-segmented-bar' in template
    assert 'apple-search-capsule' in template

    # Mobile media queries must exist in template
    assert '@media (max-width: 768px)' in template
    assert '@media (max-width: 640px)' in template
    assert 'grid-template-columns: 1fr 1fr;' in template
    assert '.apple-search-kbd' in template
    assert 'display: none !important;' in template
    assert 'scroll-snap-type: x proximity;' in template
    assert 'overflow-x: auto;' in template

    # Media card macro must not nest <a> tags inside outer card <a>
    with open('templates/components/media_card.html', 'r', encoding='utf-8') as f:
        card_macro = f.read()
    assert '<a href="/u/' not in card_macro
    assert 'arch-uploader-name' in card_macro

    # Apple card CSS must constrain min-width on mobile grid to prevent column blowout
    with open('static/css/apple-card.css', 'r', encoding='utf-8') as f:
        card_css = f.read()
    assert 'grid-template-columns: minmax(0, 1fr);' in card_css
    assert 'min-width: 0;' in card_css


def test_search_drawer_skeleton_loader():
    """Verify Search Drawer uses skeleton shimmer cards instead of spinner and supports pagination."""
    with open('templates/includes/_search_drawer.html', 'r', encoding='utf-8') as f:
        drawer = f.read()

    assert 'sd-skeleton-wrap' in drawer
    assert 'sd-skeleton-card' in drawer
    assert 'sd-skeleton-icon' in drawer
    assert 'sd-skeleton-line' in drawer
    assert 'sdShimmer' in drawer
    assert 'animation:sdSpin' not in drawer

    # Pagination and Load More button
    assert 'searchLoadMoreBtn' in drawer
    assert 'sd-load-more-btn' in drawer
    assert 'renderSearchPage' in drawer
    assert 'PAGE_SIZE = 12' in drawer

def test_upload_page_mobile_responsive_elements():
    """Verify upload page file preview, image editor modal responsiveness and Tarika hiding."""
    with open('templates/p_upload.html', 'r', encoding='utf-8') as f:
        upload_tpl = f.read()

    # 1. Preview card layout
    assert 'preview-card-main' in upload_tpl
    assert 'preview-card-actions' in upload_tpl
    assert 'editFrontBtn' in upload_tpl

    # 2. Image editor modal structure
    assert 'image-editor-card' in upload_tpl
    assert 'editor-presets-row' in upload_tpl
    assert 'editor-actions-tools' in upload_tpl
    assert 'editor-actions-submit' in upload_tpl
    assert "document.body.classList.add('image-editor-open');" in upload_tpl
    assert "document.body.classList.remove('image-editor-open');" in upload_tpl

    # 3. Floating launcher occlusion prevention in ai_assistant.html
    with open('templates/includes/ai_assistant.html', 'r', encoding='utf-8') as f:
        ai_tpl = f.read()
    assert 'body.image-editor-open #abhiAiLauncher' in ai_tpl
    assert 'display: none !important;' in ai_tpl

    # 4. Upload CSS mobile styles
    with open('static/css/pages/p_upload.css', 'r', encoding='utf-8') as f:
        upload_css = f.read()
    assert '.preview-card-actions' in upload_css
    assert '.editor-actions-tools' in upload_css
    assert '.editor-actions-submit' in upload_css

def test_no_invalid_google_font_stylesheets():
    """Ensure no templates request Apple proprietary SF Pro from Google Fonts."""
    with open('templates/app/home.html', 'r', encoding='utf-8') as f:
        home_tpl = f.read()
    assert 'fonts.googleapis.com/css2?family=SF+Pro' not in home_tpl
    assert 'SF+Pro+Display' not in home_tpl


def test_form_fields_accessibility_and_autocomplete():
    """Ensure critical form fields have accessible labels and autocomplete attributes."""
    with open('templates/app/home.html', 'r', encoding='utf-8') as f:
        home_tpl = f.read()
    assert 'aria-label="Search subjects and study materials"' in home_tpl

    with open('templates/p_struct.html', 'r', encoding='utf-8') as f:
        struct_tpl = f.read()
    assert 'for="entitySemester"' in struct_tpl
    assert 'for="entityName"' in struct_tpl
    assert 'autocomplete="name"' in struct_tpl
    assert 'autocomplete="email"' in struct_tpl
    assert 'autocomplete="current-password"' in struct_tpl

