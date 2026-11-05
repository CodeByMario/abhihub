# CSS Pipeline Migration Guide

## New Structure

```
static/css/pipeline/
  01_tokens.css       ← all design variables (single source of truth)
  02_base.css         ← reset, body, typography, animations
  03_components.css   ← buttons, cards, forms, badges, modals, share panel
  04_layout.css       ← navbar, containers, search overlay, PWA popup, footer
  05_utilities.css    ← atomic helpers (flex, spacing, text, shadow)
  pipeline.css        ← MASTER ENTRY — imports all 5 files in order

static/css/pages/
  dashboard.css       ← p_index.html specific styles
  (add more per page)
```

---

## How to Use in Templates

### In `p_struct.html` (authenticated pages) — replace ALL existing CSS links with:

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/pipeline/pipeline.css') }}">
```

Then add the page-specific CSS after it:
```html
{% block page_css %}{% endblock %}
```

In each page template:
```html
{% block page_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/dashboard.css') }}">
{% endblock %}
```

### In public pages (`p_landing.html`, `about.html`, etc.) — replace with:
```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/pipeline/pipeline.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/landing.css') }}">
```

---

## Files to REMOVE (after migration is confirmed working)

| File | Reason |
|---|---|
| `static/css/abhihub-theme.css` | Tokens → 01_tokens.css, Components → 03_components.css. Store Room CSS inside it → move to pages/store-room.css |
| `static/css/common.css` | notification-popup → 03_components.css (deduplicated) |
| `static/styles.css` | Public landing styles → pages/landing.css |
| `static/premium-cards.css` | Move to pages/premium.css |
| `methods/viewer.css` | Wrong location — should be static/css/pages/viewer.css |

## Files to KEEP as-is

| File | Reason |
|---|---|
| `static/viewer.css` | PDF.js viewer — third-party, do not touch |
| `static/css/know-me.css` | MemoryWall page — already isolated |
| `static/css/overlay-system.css` | Overlay logic — review and merge into 04_layout.css later |
| `static/css/study-pass.css` | Feature-specific — keep or move to pages/study-pass.css |
| `static/premium/css/style.css` | Premium section main styles — keep for now, gradually migrate |
| `static/css/tailwind*.css` | Tailwind utility output — keep |

---

## What Was Fixed

1. **Duplicate `:root` tokens** — removed from 3 files, now only in `01_tokens.css`
2. **`notification-popup` duplicated** in `common.css` AND `premium/css/style.css` — single definition in `03_components.css`
3. **`nav-search-overlay` fully duplicated** inside a `@media (max-width: 480px)` block — removed duplicate
4. **Store Room CSS mixed into `abhihub-theme.css`** — extracted, goes to `pages/store-room.css`
5. **`methods/viewer.css`** — misplaced Python folder, move to `static/css/pages/`
6. **Two conflicting token systems** (`--primary-light-color` in styles.css vs `--primary-600` in others) — unified under `01_tokens.css` with both brand and blue tokens
7. **`firebase-config.js` deprecated** — already marked, templates should use `supabase-config.js`

---

## Pages Still Needing CSS Files

Create these under `static/css/pages/` as you migrate:

- `landing.css`    ← `p_landing.html`
- `auth.css`       ← `p_login.html`, `p_signup.html`, `forgot_password.html`
- `profile.css`    ← `p_profile.html`
- `store-room.css` ← `p_store_room.html` (extract from abhihub-theme.css)
- `know-me.css`    ← already exists, just re-link
- `premium.css`    ← `static/premium-cards.css` content
- `upload.css`     ← `p_upload.html`
- `ranking.css`    ← `p_ranking.html`
- `viewer.css`     ← `p_view.html`, `p_pdf_reader.html`
