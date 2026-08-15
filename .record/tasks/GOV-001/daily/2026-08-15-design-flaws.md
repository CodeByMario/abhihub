# Design Flaws Audit — AbhiHub Web App
## Date: 2026-08-15
## Skill Used: `.agents/platform-design-skills-main/skills/web/SKILL.md`

## Summary

| Severity | Count |
|----------|-------|
| Critical | 5 |
| High | 6 |
| Medium | 7 |
| Low | 7 |
| **Total** | **25** |

## Critical Flaws

### 1. 163 Inline `onclick=""` Handlers
- **Severity:** Critical
- **Files:** `p_index.html` (30+), `p_upload.html` (10+), `p_landing.html` (5+), `p_struct.html` (5+), and many others
- **Issue:** Heavy use of inline event handlers violates separation of concerns. The web design skill says: "Never write `<div onclick>` when `<button>` exists."
- **Impact:** Prevents proper keyboard handling, blocks CSP rollout, unmaintainable
- **Fix:** Replace all inline handlers with `addEventListener` in external JS

### 2. Missing Skip Navigation Link
- **Severity:** Critical (WCAG SC 2.4.1)
- **Files:** `p_struct.html` (base template)
- **Issue:** No `<a href="#main" class="skip-link">` as first focusable element. Footer CSS references `.skip-nav` but never renders it
- **Fix:** Add skip link to `p_struct.html` before `<header>`

### 3. Focus Outline Management Issues
- **Severity:** Critical (WCAG SC 2.4.7)
- **Files:** `static/css/pipeline/04_layout.css`, `p_struct.html` script
- **Issue:** Notification panel JS doesn't manage focus when toggling

### 4. Color Contrast Borderline
- **Severity:** Critical (WCAG SC 1.4.3)
- **Files:** `p_index.html`, `static/css/pipeline/01_tokens.css`
- **Issue:** `--text-tertiary: #718096` and `#64748b` (gray-500) may fall below 4.5:1 on colored backgrounds

### 5. Multiple/Semantically Incorrect Landmarks
- **Severity:** Critical
- **Files:** All templates via `p_struct.html`
- **Issue:** `<main>` exists but footer/nav placement may confuse screen readers

## High Severity Flaws

### 6. `px` Font Sizes Break Text Scaling
- **Severity:** High (WCAG SC 1.4.4)
- **Files:** `video_page.html`, `contact.html`, `dino_game.html`, `know_me/` templates
- **Issue:** Web design skill: "Never set `font-size` in `px` — use `rem`"
- **Fix:** Replace all `px` font sizes with `rem`

### 7. 50+ Inline `style=""` Attributes in know_me/
- **Severity:** High
- **Files:** `know_me/dashboard.html`, `know_me/create.html`
- **Issue:** 100+ inline styles block theming, caching, maintainability
- **Fix:** Move to `.km-dashboard.css`

### 8. Placeholder-as-Label in Login Form
- **Severity:** High (WCAG SC 1.3.1, 3.3.2, 4.1.2)
- **Files:** `p_login.html` lines 86-87
- **Issue:** `<input placeholder="Email" required>` with no `<label>`
- **Fix:** Add `<label for="email-input">Email</label>`

### 9. Error Messages Not Announced
- **Severity:** High (WCAG SC 4.1.2)
- **Files:** `p_login.html` lines 82-84
- **Issue:** Error divs have `class="error-msg"` but no `role="alert"` or `aria-live`
- **Fix:** Add `role="alert" aria-live="assertive"`

### 10. Touch Target Size Concerns
- **Severity:** High (WCAG SC 2.5.5)
- **Files:** `static/css/pipeline/04_layout.css` line 208
- **Issue:** Mobile navbar items use `height: auto; padding: 6px 10px` — may produce <44px targets
- **Fix:** Ensure min 44x44px on all nav items

### 11. Missing `aria-label` on Icon-Only Buttons
- **Severity:** High
- **Files:** `p_upload.html`, `p_search.html`
- **Issue:** Buttons use `title=` only (unreliable for screen readers)
- **Fix:** Use `aria-label` instead of `title`

## Medium + Low Flaws
- No dark mode (`prefers-color-scheme` absent from CSS)
- `<button>` elements missing `type="button"` in non-form contexts
- `aria-expanded` missing on toggle buttons (notification bell, etc.)
- `overflow-x: hidden` on body hides horizontal scroll issues
- `!important` usage in print media query
- SVG icons missing `aria-hidden="true"`
- `.sr-only` class defined inline instead of in global utilities
- No cookie consent banner despite GA4 tracking
