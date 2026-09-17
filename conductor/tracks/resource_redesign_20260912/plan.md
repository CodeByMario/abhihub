# Implementation Plan: Creative UI/UX Redesign of /resource Page

## Phase Breakdown

- [x] **Phase 1: Comprehensive Audit & Functional Element Cataloging**
  - [x] Identify tech stack (Flask + Jinja2 + Vanilla CSS Pipeline + Vanilla JS).
  - [x] Catalog all 18 ground-truth functional elements (like/bookmark, share, comment posting, AI chat, PDF/Image controls, report modal, etc.).
  - [x] Formulate 2 distinct design directions in `spec.md`.

- [x] **Phase 2: User Design Direction Selection & Structural Scaffold**
  - [x] User selected **Direction 1: Immersive Focus Workspace (70/30 Split Canvas with Tabbed Productivity Sidebar)**.
  - [x] Refactor `templates/resource.html` grid and semantic HTML markup according to Direction 1.

- [x] **Phase 3: Visual Styling & UI Component Polish**
  - [x] Implement global CSS variables, dark mode styles, typography hierarchy, card elevations, hover/active states, and glassmorphic panels.
  - [x] Polish PDF iframe viewer, Image canvas, comment list, AI OCR assistant panel, and bottom CTA banner.
  - [x] Create sticky tabbed productivity sidebar for AI Study Assistant and Resource Details.

- [x] **Phase 4: Mobile Ergonomics, Touch & Safe Area Polish**
  - [x] Ensure fluid responsive breakpoints across mobile (375px+), tablet (768px+), and desktop (1024px+).
  - [x] Enforce ~44px minimum tap targets for touch controls (zoom buttons, action pills, persona chips, suggestion chips, send button, report FAB).
  - [x] Integrate safe area inset handling (`env(safe-area-inset-bottom)`) for notch and home-bar devices.

- [x] **Phase 5: Functional Verification & Zero-Regression Testing**
  - [x] Re-verify all 18 functional inventory items against the new Immersive Focus Workspace layout.
