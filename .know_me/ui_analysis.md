# AbhiHub UI & UX Consistency Analysis

## 1. Grid & Page Layout Rules
- **Container widths**: Public pages use `.container` (Bootstrap-styled). Private application layout uses a responsive width maxing out at `1200px` for main contents.
- **Side paddings**: Public layout uses Bootstrap standard paddings. Dashboard layout uses `--space-6` (1.5rem) side padding.
- **Bottom margin**: Dashboards and active routes use a bottom padding of `--space-20` (5rem) or similar to prevent overlapping the fixed bottom navigation bar (`p_nav.html`).
- **Breakpoints**: Standard Bootstrap media queries are used: `@media (max-width: 768px)` for mobile collapse, and `@media (min-width: 640px)` for tablet sizing.

## 2. Branding & Color Systems
- **Color Palettes**:
  - Primary text: `--text-primary` (`#1a202c` / dark gray)
  - Secondary text: `--text-secondary` (`#4a5568`)
  - Tertiary text: `--text-tertiary` (`#718096`)
  - Primary UI background: `--background-primary` (`#fefefe`) or `--gradient-surface` (`linear-gradient(135deg, #fefefe, #f8fafc)`)
  - Border light color: `--border-light` (`#e2e8f0`)
  - Card background: `--surface` (`#ffffff`)
- **Brand Gradients**:
  - Primary Gradient: `linear-gradient(135deg, #FFE769, #62EEA8)` (Yellow to green)
  - Secondary Gradient: `linear-gradient(135deg, #FFE4BA, #FFE769)` (Orange/Peach to yellow)

## 3. Typography
- **Core Font**: `Kanit`, sans-serif (via Google Fonts).
- **Body rules**: Defaults to `font-family: "Kanit", -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;` with `line-height: 1.6`.
- **Text sizes**: Uses spacing and font scales:
  - `--text-sm` (0.875rem) for minor labels.
  - `--text-base` (1rem) for body copy.
  - `--text-xl` (1.25rem) for section subtitles.
  - `--text-2xl` (1.5rem) / `--text-3xl` (1.875rem) for primary headings.
  - Display headings use Bootstrap font weights (`fw-bold`, `display-4`).

## 4. UI Elements & Cards
- **Card shape**: Rounded corners using `--radius-2xl` (`1.5rem` / `24px`) or `--radius-xl` (`1rem`).
- **Shadows**: Soft shadows like `--shadow-sm` (`0 1px 3px rgba(0,0,0,0.1)`) and `--shadow-lg` (`0 10px 15px -3px rgba(0,0,0,0.1)`).
- **Hover effects**:
  - `transform: translateY(-2px)` or `transform: translateY(-4px)`
  - Transition duration: `--transition-normal` (`0.25s cubic-bezier(0.4, 0, 0.2, 1)`)
  - Borders change color on hover to `--primary-200` or custom gradients.
- **Buttons**:
  - Large touch targets (minimum 48px height on mobile).
  - Background gradients matching the brand or solid accents (`--primary-600` / `#2563eb`).
  - Border radius: `--radius-full` (`9999px`) or `--radius-lg` (`0.75rem`).

## 5. Navigation & Structural Integrations
- **Public Header**: Simple transparent/light Bootstrap navbar (`navbar_public.html`) with the AbhiHub logo (`/static/images/logo.png`, `height="40"`).
- **Authenticated Header/Footer**: Standard `p_nav.html` bottom mobile navbar, and standard dark background Bootstrap footer (`footer.html`) for public pages.
