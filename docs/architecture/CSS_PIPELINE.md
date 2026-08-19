AbhiHub CSS Pipeline — Complete Summary
What Was Built
New Folder Structure
static/css/pipeline/
  01_tokens.css          ← ALL design variables (colors, spacing, fonts, shadows, gradients)
  02_base.css            ← Reset, body, typography, scrollbar, selection, animations
  app-shell.css          ← Header, main-nav, logo, main content area, popup
  03_components.css      ← Buttons, cards, forms, badges, modals, share panel, skeleton
  04_layout.css          ← Bottom navbar, containers, search overlay, footer
  05_utilities.css       ← Atomic helpers (flex, spacing, text, shadows, display)
  feature-tour.css       ← Feature tour overlay & tooltip
  pwa-install.css        ← PWA install popup
  promo.css              ← Promo announcement strip + promo card modal
  profile-nudge.css      ← Profile completion & notifications nudge overlay
  notification-bell.css  ← Header bell + dropdown panel
  pipeline.css           ← MASTER ENTRY — imports all 11 files in correct order
  MIGRATION.md           ← Step-by-step migration guide

static/css/pages/
  dashboard.css          ← p_index.html specific styles

Copy
What Was Fixed in p_struct.html
Before	After
7 inline <style> blocks (~400 lines)	0 inline <style> blocks
3 wrong CSS <link> tags	1 pipeline link + 2 utility links
onmouseover/onmouseout hover hacks on bell button	Pure CSS hover in notification-bell.css
300+ lines of style= on HTML elements (nudge overlay, bell panel)	All replaced with CSS classes
Notification items rendered with hardcoded style= in JS template literals	Now use .notif-item, .notif-item-icon, .notif-item-content etc.
Duplicate :root token blocks across 3+ files	Single source in 01_tokens.css
notification-popup defined in 2 files	Single definition in 03_components.css
Feature tour styles duplicated in 04_layout.css AND feature-tour.css	Removed from 04_layout.css, lives only in feature-tour.css
PWA install styles duplicated with conflicting z-index (1000 vs 9999)	Removed from 04_layout.css, lives only in pwa-install.css
promoBounce animation used in profile-nudge.css but defined elsewhere	Added self-contained copy in profile-nudge.css
How to Use
In p_struct.html <head> (already done):
<link rel="stylesheet" href="{{ url_for('static', filename='css/pipeline/pipeline.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/overlay-system.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.min.css') }}">

Copy
html
For page-specific CSS, add after the pipeline:
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/dashboard.css') }}">

Copy
html
Files Still Needed (not yet migrated)
These pages still need their own CSS files under static/css/pages/:

Page file	Needs
p_landing.html	pages/landing.css
p_login.html, p_signup.html	pages/auth.css
p_profile.html	pages/profile.css
p_store_room.html	pages/store-room.css (extract from abhihub-theme.css)
p_upload.html	pages/upload.css
p_ranking.html	pages/ranking.css
p_view.html, p_pdf_reader.html	pages/viewer.css
know_me/ templates	already has css/know-me.css, just re-link
Old Files That Can Be Deleted (after testing)
File	Why
static/css/abhihub-theme.css	Tokens → 01_tokens.css, Store Room CSS → pages/store-room.css
static/css/common.css	notification-popup → 03_components.css
static/premium/css/style.css	All app shell + component styles migrated to pipeline
static/premium-cards.css	Move to pages/premium.css when ready
methods/viewer.css	Wrong location — move to static/css/pages/viewer.css
Quick Reference — Which Class Lives Where
Class	File
--primary-*, --space-*, --radius-* etc.	01_tokens.css
body, h1-h6, a, ::selection, @keyframes	02_base.css
header, .main-nav, .logo, .logo-text, main, .popup	app-shell.css
.btn, .card, .form-input, .badge, .notification-popup	03_components.css
.navbar, .container, .nav-search-overlay, .site-footer	04_layout.css
.d-flex, .mt-4, .text-center, .cursor-pointer	05_utilities.css
#featureTourOverlay, .ft-highlight	feature-tour.css
.pwa-install-popup, .pwa-popup-*	pwa-install.css
#promoStrip, #promoCard, .promo-*	promo.css
#profileNudgeOverlay, .nudge-*	profile-nudge.css
#notifBell, #notifPanel, .notif-*	notification-bell.css
.file-card, .interaction-bar, .updates-carousel	pages/dashboard.css
.study-pass-toast, .gate-card	css/study-pass.css (existing, kept)


@Pin Context
Active file

Rules
