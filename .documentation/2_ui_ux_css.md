# UI & UX / CSS Documentation — AbhiHub

## Layout System

| Context | Rule |
|---|---|
| Public pages | Bootstrap `.container` with standard gutters |
| Authenticated app | Max width `1200px`, side padding `--space-6` (1.5rem) |
| Bottom padding | `--space-20` (5rem) to avoid overlap with bottom nav |
| Mobile breakpoint | `@media (max-width: 768px)` |
| Tablet breakpoint | `@media (min-width: 640px)` |

---

## Color Variables

```css
--text-primary:       #1a202c;   /* dark gray */
--text-secondary:     #4a5568;
--text-tertiary:      #718096;
--background-primary: #fefefe;
--gradient-surface:   linear-gradient(135deg, #fefefe, #f8fafc);
--border-light:       #e2e8f0;
--surface:            #ffffff;
```

### Brand Gradients
```css
/* Primary — Yellow to Green */
linear-gradient(135deg, #FFE769, #62EEA8)

/* Secondary — Peach to Yellow */
linear-gradient(135deg, #FFE4BA, #FFE769)
```

---

## Typography

- Core font: `Kanit`, sans-serif (Google Fonts)
- Fallback: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- Line height: `1.6`

| Variable | Size | Usage |
|---|---|---|
| `--text-sm` | 0.875rem | Labels, minor text |
| `--text-base` | 1rem | Body copy |
| `--text-xl` | 1.25rem | Section subtitles |
| `--text-2xl` | 1.5rem | Headings |
| `--text-3xl` | 1.875rem | Primary headings |
| `display-4` | Bootstrap | Hero/display headings |

---

## Cards & UI Elements

```css
/* Border radius */
--radius-sm:   0.375rem
--radius-lg:   0.75rem
--radius-xl:   1rem
--radius-2xl:  1.5rem  (24px) — default card radius
--radius-full: 9999px  — pills/buttons

/* Shadows */
--shadow-sm: 0 1px 3px rgba(0,0,0,0.1)
--shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1)

/* Hover effect */
transform: translateY(-2px) or translateY(-4px)
transition: --transition-normal (0.25s cubic-bezier(0.4, 0, 0.2, 1))
```

---

## Buttons

- Min height: `48px` on mobile (touch target)
- Radius: `--radius-full` for pill buttons, `--radius-lg` for square-ish
- Background: brand gradient or `--primary-600` (`#2563eb`)

---

## CSS File Map

| File | Purpose |
|---|---|
| `static/premium/css/style.css` | Main app styles (v2.0.1) |
| `static/css/common.css` | Shared base styles |
| `static/css/overlay-system.css` | Overlay/modal system |
| `static/css/tailwind.min.css` | Tailwind utility classes |
| `static/css/abhihub-theme.css` | Brand theme tokens |
| `static/css/study-pass.css` | Study Pass feature styles |
| `static/css/know-me.css` | Know Me / MemoryWall styles |
| `static/css/p_index.css` | Dashboard page |
| `static/css/p_landing.css` | Landing page |
| `static/css/p_login.css` | Login page |
| `static/css/p_profile.css` | Profile page |
| `static/css/p_signup.css` | Signup page |
| `static/css/pwa-install.css` | PWA install prompt |
| `static/css/join.css` | Join/onboarding page |
| `static/premium-cards.css` | Premium card components |
| `static/styles.css` | Global public styles |
| `static/viewer.css` | PDF viewer styles |
| `methods/viewer.css` | Viewer method styles |

## Migration Rules

- Record migration progress in `.my work process/`.
- Keep CSS architecture and UI documentation in `.documentation/`.
- Extract page-specific CSS into `static/css/pages/<page>.css`.
- Prefer page-specific CSS files over inline `<style>` blocks in templates.
- Keep `style=` attributes only for dynamic, runtime-only values and plan to replace them with class rules later.

---

## Navigation Components

| Component | File | Used On |
|---|---|---|
| Bottom mobile nav (auth) | `templates/p_nav.html` | All authenticated pages |
| Public navbar | `templates/navbar_public.html` | Unauthenticated pages |
| Premium navbar | `templates/includes/_navbar_premium.html` | Premium section |
| Footer | `templates/footer.html` | Public pages only |

### Bottom Nav Items
1. Home → `/dashboard`
2. Ranking → `/ranking`
3. Upload (FAB center) → `/upload`
4. Account → `/account`
5. Store Room → `/store-room`
6. Admin (conditional) → `/admin`

---

## Master Layout

- File: `templates/p_struct.html` (1391 lines)
- All authenticated pages use this as base
- Includes: Google Fonts, GA4 tag, PWA install popup, profile nudge overlay, promo card overlay
- Exposes session user to JS: `window.__CURRENT_USER__`

---

## Tailwind Config

- Config: `tailwind.config.js`
- Input: `static/css/tailwind-input.css`
- Output: `static/css/tailwind-full.min.css`
- Usage: Minimal — mostly utility classes alongside custom CSS

## Progress tracking

- `p_account.html`: removed embedded CSS, page-specific CSS linked.
- `p_file_receiver.html`: page-specific CSS linked, inline JS remains.
- `p_index.html`: removed embedded head styles, welcome section CSS partially extracted.
- Next: remove remaining inline styles and move page-specific layouts to CSS files.
