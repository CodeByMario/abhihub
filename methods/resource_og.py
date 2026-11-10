import os
import io
from PIL import Image, ImageDraw, ImageFont

# In-memory cache for generated OG images (doc_id -> bytes)
_OG_CACHE = {}
_MAX_CACHE_SIZE = 250


def _get_font(bold=False, size=24):
    font_candidates = [
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
        os.path.join(os.path.dirname(__file__), "..", "static", "pdfjs-6.1.200-dist", "web", "standard_fonts", "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def generate_resource_og_image(data: dict) -> bytes:
    """
    Generates a 1200x630 branded AbhiHub dynamic Open Graph image for a study resource.
    Cached in-memory to prevent repeated generation overhead.
    """
    doc_id = str(data.get('id') or data.get('doc_id') or '')
    title = str(data.get('title') or 'Study Material').strip()
    subject = str(data.get('subject') or 'General Engineering').strip()
    author = str(data.get('author') or 'AbhiHub Community').strip()
    semester = str(data.get('semester') or 'All Semesters').strip()
    category = str(data.get('category') or 'Notes').strip().upper()
    college = str(data.get('college') or 'Engineering Hub').strip()

    cache_key = f"{doc_id}:{title[:30]}:{subject[:20]}:{category}:{semester}"
    if cache_key in _OG_CACHE:
        return _OG_CACHE[cache_key]

    w, h = 1200, 630
    img = Image.new('RGB', (w, h), color='#f4f0ff')
    draw = ImageDraw.Draw(img, 'RGBA')

    # Gradient background simulation
    for y_pos in range(h):
        ratio = y_pos / h
        r = int(255 * (1 - ratio) + 238 * ratio)
        g = int(255 * (1 - ratio) + 233 * ratio)
        b = int(255 * (1 - ratio) + 255 * ratio)
        draw.line([(0, y_pos), (w, y_pos)], fill=(r, g, b, 255))

    # Decorative background circles
    draw.ellipse([1120 - 250, 30 - 250, 1120 + 250, 30 + 250], fill=(232, 221, 255, 230))
    draw.ellipse([0 - 220, 630 - 220, 0 + 220, 630 + 220], fill=(245, 241, 255, 230))

    # Fonts
    f_brand_logo = _get_font(bold=True, size=46)
    f_brand = _get_font(bold=True, size=42)
    f_sub = _get_font(bold=True, size=13)
    f_tag = _get_font(bold=True, size=20)
    f_badge = _get_font(bold=True, size=18)
    f_title = _get_font(bold=True, size=42)
    f_label = _get_font(bold=True, size=14)
    f_val = _get_font(bold=True, size=24)
    f_sem = _get_font(bold=True, size=19)
    f_foot = _get_font(bold=True, size=20)

    # 1. Header Card
    draw.rounded_rectangle([45, 30, 1155, 120], radius=20, fill='#ffffff', outline='#e2d9f3', width=1)
    # Brand logo symbol & text
    draw.text((70, 50), "Abhi", fill='#17152c', font=f_brand)
    # Measure "Abhi" to place "Hub"
    draw.text((172, 50), "Hub", fill='#6834d5', font=f_brand)
    draw.text((72, 95), "NOTES  |  PYQs  |  PRACTICALS", fill='#68627c', font=f_sub)
    draw.text((780, 62), "YOUR COLLEGE STUDY HUB", fill='#6834d5', font=f_tag)

    # 2. Main Content Card
    draw.rounded_rectangle([55, 145, 1145, 525], radius=26, fill='#ffffff', outline='#ded5f0', width=1)

    # Category Badge (Notes / PYQ / Practical)
    badge_w = max(160, int(len(category) * 13) + 40)
    draw.rounded_rectangle([95, 172, 95 + badge_w, 212], radius=16, fill='#eee7ff')
    draw.text((115, 182), category, fill='#6834d5', font=f_badge)

    # Word wrapping for Title
    words = title.split()
    lines = []
    cur_line = ""
    max_title_w = 980
    for word in words:
        test = f"{cur_line} {word}".strip()
        # approximate length check or draw.textlength
        try:
            line_w = draw.textlength(test, font=f_title)
        except Exception:
            line_w = len(test) * 22
        if line_w > max_title_w and cur_line:
            lines.append(cur_line)
            cur_line = word
            if len(lines) >= 2:
                break
        else:
            cur_line = test
    if cur_line and len(lines) < 2:
        lines.append(cur_line)
    elif cur_line and len(lines) >= 2:
        lines[1] = lines[1][:45] + "..."

    # Draw Title Lines
    t_y = 232
    for line in lines:
        draw.text((95, t_y), line, fill='#17152c', font=f_title)
        t_y += 52

    # Subject & Semester Row
    draw.text((95, 360), "SUBJECT", fill='#77718b', font=f_label)
    sub_text = subject[:40]
    draw.text((95, 382), sub_text, fill='#6834d5', font=f_val)

    sem_box_text = f"SEMESTER: {semester}".upper()
    sem_w = int(len(sem_box_text) * 11) + 40
    draw.rounded_rectangle([1100 - sem_w, 365, 1100, 412], radius=14, fill='#f0ebff')
    draw.text((1120 - sem_w, 377), sem_box_text, fill='#38236c', font=f_sem)

    # Divider line
    draw.line([(95, 442), (1100, 442)], fill='#eae3f5', width=2)

    # Shared by & College row (two-column layout)
    draw.text((95, 458), "UPLOADED BY", fill='#77718b', font=f_label)
    draw.text((95, 480), author[:32], fill='#17152c', font=f_val)

    draw.text((620, 458), "COLLEGE / INSTITUTION", fill='#77718b', font=f_label)
    coll_text = college[:36]
    draw.text((620, 480), coll_text, fill='#6834d5', font=f_val)

    # 3. Footer Bar
    draw.rectangle([0, 555, w, h], fill='#30206c')
    draw.text((65, 582), "abhihub.edu.eu.org", fill='#ffffff', font=f_foot)
    draw.text((680, 582), "Discover  •  Study  •  Share  •  Grow", fill='#e0d5ff', font=f_foot)

    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    img_bytes = buf.getvalue()

    if len(_OG_CACHE) >= _MAX_CACHE_SIZE:
        _OG_CACHE.clear()
    _OG_CACHE[cache_key] = img_bytes
    return img_bytes
