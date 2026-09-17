# Track Specification: Creative UI/UX Redesign of /resource Page

## Objective
Execute a comprehensive, design-led presentation layer redesign of the `/resource` page (`templates/resource.html`). The redesign will establish a state-of-the-art UI/UX, superior visual hierarchy, and modern responsive ergonomics across mobile, tablet, and desktop viewports, while preserving 100% of all existing Flask routes, Jinja data contracts, JavaScript handlers, and API endpoints.

## Tech Stack
- **Backend / Templating**: Python / Flask, Jinja2 template inheritance (`templates/resource.html` extending `p_struct.html`).
- **CSS Architecture**: Vanilla CSS pipeline based on `static/css/pipeline/01_tokens.css`.
- **Client Libraries**: Vanilla JS (PDF.js viewer iframe, Image canvas viewer with touch/drag/zoom), `marked.min.js`, `html2pdf.js`, Web Share API, fetch API interactions.

## Immutable Functional Inventory (Ground Truth)
The following 18 functional/interactive elements must be preserved with 100% fidelity:
1. **Breadcrumbs Navigation**: Dynamic links to `/`, `/college/<slug>/files`, `/subject/<slug>`.
2. **Like Button**: `data-action="toggleLike"`, `data-doc-id="{{ document.id }}"`, `<span class="like-count">`.
3. **Bookmark / Save Button**: `data-action="toggleBookmark"`, `data-doc-id="{{ document.id }}"`, `<span class="bookmark-count">`.
4. **Comments Link & Counter**: `#commentsSection` anchor with `#metaCommentCount` and `#commentsCountBadge`.
5. **Share Resource Trigger**: `onclick="shareResource()"` (Web Share API with clipboard fallback).
6. **Doc Card Fullscreen Focus Mode**: `onclick="toggleDocCardFullscreen()"` (toggles `.fullscreen-doc-card`).
7. **PDF Document Previewer**: PDF.js iframe (`viewer.html?file=/api/view-doc/...`) with `#pdfLoadingBar` & progress status.
8. **Image Document Previewer & Controls**:
   - Zoom controls (`zoomInImage`, `zoomOutImage`, `resetImageZoom`, `#ivZoomLabel`).
   - Fullscreen toggle (`toggleImageFullscreen`).
   - Canvas `#imageCanvas` with skeleton `#imageSkeleton`, error box `#imageError`, image `#previewImage` (`/api/view-doc/...`), watermark `.image-watermark`, logo badge `.image-watermark-logo`.
   - Wheel zoom, drag pan, double click, pinch touch, and escape key event handlers.
9. **Academic Overview & SEO Metadata Card**: Schema.org JSON-LD structured data, difficulty badge, description text, key topics list, uploader note, academic context card.
10. **Community Discussion & Comments Card**:
    - Input `#newCommentInput`, submit `#submitCommentBtn` with `onclick="submitComment()"`.
    - Logged-out state link to `/login?next=...`.
    - Comments container `#commentsList` loaded via `/api/interactions/comments/{{ document.id }}`.
11. **About Resource & Contributor Card**: Title, Category, Subject link, Institution link, Uploader name, verified badge.
12. **AI Vision & OCR Assistant Card**:
    - WhatsApp Share button `shareChatWhatsApp()`.
    - PDF Export button `exportChatPDF()`.
    - Fullscreen Toggle button `toggleChatFullscreen()`.
    - Persona buttons (ChatGPT, Gemini, Claude) `sendPersonaPrompt()`.
    - Suggestion chips `suggestQ()`.
    - Model selector `#aiModelSelect`.
    - Input `#aiQuestion` & submit button `#aiSendBtn` with `askAI()`.
    - Rank Gate overlay `.ai-rank-gate`.
13. **Suggested & Store Room Resources Grid**: Links to `/resource/{{ s_doc.id }}`.
14. **Resource Upload CTA Banner**: Link to `url_for('upload')`.
15. **Report Issue FAB & Modal**:
    - FAB button `.r-report-fab` / `rOpenReport()`.
    - Sheet backdrop `#rReportBackdrop`, select `#rReportType`, message `#rReportMsg`, submit `#rReportBtn` / `rSubmitReport()`.

---

## Proposed Design Directions for User Selection

### Direction 1: "Immersive Focus Workspace" (Modern Split Canvas Architecture) [RECOMMENDED]
- **Layout & Structure**: A 2-pane productivity workspace layout on desktop/tablet (70% primary reading canvas / 30% tabbed interactive sidebar).
- **Visual Aesthetic**: Sleek dark/light hybrid with high-contrast preview canvas (`#0f172a`), electric blue `#3b82f6` & emerald `#10b981` accents, glassmorphic floating control pills (`backdrop-filter: blur(12px)`), crisp Kanit typography scale.
- **Productivity Sidebar**: Tabbed interface switching between **AI Assistant**, **Discussion & Comments**, and **Resource Details**.

### Direction 2: "Editorial Knowledge Hub" (Linear Storytelling & Floating Glass Dock)
- **Layout & Structure**: Content-first editorial layout featuring a prominent full-width hero header, centered stage previewer card, 2-column details & overview grid, and a bottom floating glass action dock.
- **Visual Aesthetic**: Warm indigo & slate canvas with multi-layered depth (`0 20px 40px rgba(0,0,0,0.06)`), smooth card borders, spacious margins, and persistent bottom action bar (Like, Save, Share, AI, Report).
