# AbhiHub Frontend Error & Audit Report
**Date:** May 18, 2026
**Scope:** HTML Templates, CSS, and JavaScript files

## 🔴 High Severity Issues

### 1. Viewport & Accessibility Constraints
- **File:** `templates/p_struct.html`
- **Issue:** Previously used `maximum-scale=1` and `user-scalable=no` which breaks WCAG guidelines for zooming.
- **Status:** **Resolved** in recent patch.

### 2. Missing Vendor Prefixes for Safari
- **File:** `templates/p_struct.html`
- **Issue:** `backdrop-filter` lacked `-webkit-backdrop-filter`, causing broken glassmorphism effects on iOS Safari.
- **Status:** **Resolved** in recent patch.

## 🟡 Medium Severity Issues

### 1. Excessive Inline CSS
- **Files Affected:** 
  - `templates/p_struct.html`
  - `templates/p_index.html`
  - `templates/p_view.html`
  - `templates/p_upload.html`
  - `templates/admin_notification_panel.html`
  - and several other templates.
- **Issue:** Over-reliance on `style="..."` attributes rather than class-based utility or component CSS. This leads to code bloat, difficulty in overriding styles, and poor maintainability.
- **Recommendation:** Extract inline styles into `static/css/p_index.css` or leverage existing Tailwind utility classes if available.

### 2. Overuse of `!important` in CSS
- **Files Affected:**
  - `static/css/p_index.css`
- **Issue:** Widespread use of `!important` found during scan. This breaks CSS specificity rules and makes future UI updates fragile and difficult to debug.
- **Recommendation:** Refactor CSS specificity using stronger selectors or CSS custom properties (variables) instead of relying on `!important`.

### 3. PromoStrip Layout & DOM Reflows
- **Files Affected:** `templates/p_struct.html`
- **Issue:** The promo strip hiding logic required a `setTimeout` to safely apply `display: none` after a CSS transition. While functional, mixing JS timeouts with CSS transitions can sometimes cause race conditions on slower devices.
- **Recommendation:** Consider using the `transitionend` event listener instead of a hardcoded 300ms timeout.

## 🟢 Low Severity / Tech Debt

### 1. Render-Blocking Resources
- **Issue:** Some scripts and styles are loaded synchronously in the `<head>` blocking the first paint.
- **Recommendation:** Add `defer` or `async` to non-critical external JavaScript files to improve Core Web Vitals (LCP/FCP).

### 2. CSS Bundle Optimization
- **Issue:** Mix of Tailwind CSS (`tailwind.min.css`) and custom CSS (`p_index.css`). Tailwind is designed to be built via PostCSS to purge unused styles. If a full CDN build is used, it severely impacts page load size.
- **Recommendation:** Integrate a proper build step to compile and purge unused Tailwind CSS for production.
