path = 'templates/college.html'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

old_college_css = """:root { --college-ink:#0f172a; --college-muted:#64748b; --college-line:#e2e8f0; --college-blue:#2563eb; --college-bg:#f8fafc; }
  body { background:var(--college-bg); }
  .college-page { max-width:1180px; margin:0 auto; padding:1rem 1.25rem 5rem; color:var(--college-ink); }
  .college-hero { display:flex; justify-content:space-between; gap:2rem; align-items:flex-end; padding:2.5rem; border-radius:24px; color:#fff; background:linear-gradient(135deg,#0f172a,#1d4ed8); box-shadow:0 20px 45px rgba(30,64,175,.22); }
  .college-kicker { color:#bfdbfe; font-size:.75rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; }
  .college-hero h1 { margin:.55rem 0 .75rem; font-size:clamp(2rem,5vw,3.8rem); line-height:1.04; letter-spacing:-.04em; }
  .college-hero p { max-width:700px; margin:0; color:#dbeafe; line-height:1.6; }
  .college-actions { display:flex; flex-wrap:wrap; gap:.7rem; margin-top:1.4rem; }
  .college-action { display:inline-flex; align-items:center; justify-content:center; min-height:44px; padding:.7rem 1rem; border-radius:10px; text-decoration:none; font-weight:800; }
  .college-action.primary { background:#fff; color:#1d4ed8; }
  .college-action.secondary { border:1px solid rgba(255,255,255,.3); color:#fff; }
  .college-location { white-space:nowrap; align-self:flex-start; padding:.55rem .8rem; border:1px solid rgba(255,255,255,.25); border-radius:999px; color:#dbeafe; font-size:.85rem; font-weight:700; }
  .college-stats { display:grid; grid-template-columns:repeat(3,1fr); gap:1rem; margin:-1.6rem 1.5rem 2.8rem; position:relative; }
  .college-stat { background:#fff; border:1px solid var(--college-line); border-radius:16px; padding:1.15rem; box-shadow:0 12px 30px rgba(15,23,42,.08); }
  .college-stat strong { display:block; font-size:1.8rem; color:var(--college-blue); }
  .college-stat span { color:var(--college-muted); font-size:.75rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
  .college-section { margin-top:2.5rem; }
  .college-section-head { display:flex; justify-content:space-between; gap:1rem; align-items:end; margin-bottom:1rem; }
  .college-section h2 { margin:0; font-size:1.5rem; letter-spacing:-.03em; }
  .college-section-head p { margin:.35rem 0 0; color:var(--college-muted); }
  .college-link { color:var(--college-blue); font-weight:800; text-decoration:none; }
  .college-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:1rem; }
  .college-card { display:flex; flex-direction:column; min-height:160px; padding:1.1rem; background:#fff; border:1px solid var(--college-line); border-radius:16px; color:inherit; text-decoration:none; transition:.2s ease; }
  .college-card:hover, .college-card:focus-visible { transform:translateY(-3px); border-color:#93c5fd; box-shadow:0 14px 28px rgba(37,99,235,.12); outline:none; }"""

new_college_css = """:root {
    --college-ink: #1D1D1F;
    --college-muted: #6E6E73;
    --college-line: rgba(0, 0, 0, 0.08);
    --college-blue: #0071E3;
    --college-bg: #F5F5F7;
    --college-card: #FFFFFF;
    --college-pill: 980px;
  }
  [data-theme="dark"], .dark {
    --college-ink: #F5F5F7;
    --college-muted: #8E8E93;
    --college-line: rgba(255, 255, 255, 0.12);
    --college-blue: #0071E3;
    --college-bg: #000000;
    --college-card: #1C1C1E;
  }
  body { background:var(--college-bg); font-family: -apple-system, BlinkMacSystemFont, "Plus Jakarta Sans", sans-serif; }
  .college-page { max-width:1180px; margin:0 auto; padding:1.5rem 1.25rem 5rem; color:var(--college-ink); }
  .college-hero { display:flex; justify-content:space-between; gap:2rem; align-items:flex-end; padding:2.75rem; border-radius:24px; color:#fff; background:#1D1D1F; box-shadow:0 14px 38px rgba(0,0,0,.15); }
  .college-kicker { color:#86868B; font-size:.78rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
  .college-hero h1 { margin:.55rem 0 .75rem; font-size:clamp(2rem,5vw,3.5rem); line-height:1.06; letter-spacing:-.03em; font-weight:700; }
  .college-hero p { max-width:700px; margin:0; color:#A1A1A6; line-height:1.6; font-size:1.05rem; }
  .college-actions { display:flex; flex-wrap:wrap; gap:.75rem; margin-top:1.75rem; }
  .college-action { display:inline-flex; align-items:center; justify-content:center; min-height:44px; padding:.7rem 1.5rem; border-radius:var(--college-pill); text-decoration:none; font-weight:600; font-size:0.95rem; transition: all .2s cubic-bezier(0.16, 1, 0.3, 1); }
  .college-action.primary { background:#0071E3; color:#fff !important; box-shadow:0 4px 14px rgba(0,113,227,.35); }
  .college-action.primary:hover { background:#0077ED; transform:scale(1.02); }
  .college-action.secondary { border:1.5px solid rgba(255,255,255,.35); color:#fff; background:transparent; }
  .college-action.secondary:hover { background:rgba(255,255,255,.1); transform:scale(1.02); }
  .college-location { white-space:nowrap; align-self:flex-start; padding:.45rem .95rem; border:1px solid rgba(255,255,255,.2); border-radius:var(--college-pill); color:#D2D2D7; font-size:.85rem; font-weight:600; background:rgba(255,255,255,.06); backdrop-filter:blur(10px); }
  .college-stats { display:grid; grid-template-columns:repeat(3,1fr); gap:1.25rem; margin:-1.6rem 1.5rem 2.8rem; position:relative; }
  .college-stat { background:var(--college-card); border:1px solid var(--college-line); border-radius:18px; padding:1.25rem 1.5rem; box-shadow:0 4px 20px rgba(0,0,0,.04); }
  .college-stat strong { display:block; font-size:2rem; color:var(--college-blue); font-variant-numeric:tabular-nums; font-weight:800; }
  .college-stat span { color:var(--college-muted); font-size:.75rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; }
  .college-section { margin-top:3rem; }
  .college-section-head { display:flex; justify-content:space-between; gap:1rem; align-items:end; margin-bottom:1.25rem; }
  .college-section h2 { margin:0; font-size:1.6rem; letter-spacing:-.02em; font-weight:700; }
  .college-section-head p { margin:.35rem 0 0; color:var(--college-muted); }
  .college-link { color:var(--college-blue); font-weight:600; text-decoration:none; display:inline-flex; align-items:center; gap:0.25rem; }
  .college-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:1.25rem; }
  .college-card { display:flex; flex-direction:column; min-height:160px; padding:1.35rem; background:var(--college-card); border:1px solid var(--college-line); border-radius:18px; color:inherit; text-decoration:none; transition: all .2s cubic-bezier(0.16, 1, 0.3, 1); box-shadow:0 2px 12px rgba(0,0,0,.03); }
  .college-card:hover, .college-card:focus-visible { transform:translateY(-3px); border-color:var(--college-blue); box-shadow:0 12px 28px rgba(0,113,227,.15); outline:none; }"""

text = text.replace(old_college_css.replace('\n', '\r\n'), new_college_css.replace('\n', '\r\n'))
text = text.replace(old_college_css, new_college_css)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated college.html successfully")
