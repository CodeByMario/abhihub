import io
import os
import re
from PIL import Image, ImageDraw, ImageFont
from config.brand import BRAND_CONFIG

_OG_CACHE = {}
_MAX_CACHE_SIZE = 500


def _get_font(bold=False, size=24):
    font_candidates = [
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "static",
            "pdfjs-6.1.200-dist",
            "web",
            "standard_fonts",
            "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf",
        ),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
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


def _draw_header(draw, active_pill="ACADEMIC HUB"):
    f_brand_bold = _get_font(bold=True, size=40)
    f_sub = _get_font(bold=False, size=14)
    f_pill = _get_font(bold=True, size=15)

    # Top brand card
    draw.rounded_rectangle([50, 35, 1150, 115], radius=18, fill="#131c31", outline="#22324f", width=1)
    # Brand logo text: Abhi (white) + Hub (blue)
    draw.text((75, 48), "Abhi", fill="#ffffff", font=f_brand_bold)
    draw.text((168, 48), "Hub", fill=BRAND_CONFIG["colors"]["primary"], font=f_brand_bold)
    draw.text((77, 92), BRAND_CONFIG["tagline"].upper(), fill="#94a3b8", font=f_sub)

    # Active tag pill on right
    pill_text = str(active_pill).upper()[:28]
    pill_w = max(130, len(pill_text) * 11 + 30)
    draw.rounded_rectangle([1125 - pill_w, 53, 1125, 97], radius=12, fill="#1e293b", outline="#334155")
    draw.text((1140 - pill_w, 66), pill_text, fill="#38bdf8", font=f_pill)


def _draw_footer(draw):
    f_foot = _get_font(bold=False, size=18)
    f_domain = _get_font(bold=True, size=19)
    # Bottom brand footer bar
    draw.rectangle([0, 565, 1200, 630], fill="#080c15")
    draw.line([(0, 565), (1200, 565)], fill="#1e293b", width=1)
    draw.text((60, 586), BRAND_CONFIG["watermark"], fill="#ffffff", font=f_domain)
    draw.text((680, 586), "Download PYQs  •  Share Notes  •  Earn Royalties", fill="#94a3b8", font=f_foot)


def _render_image_to_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def generate_home_og() -> bytes:
    cache_key = "home_og_v1"
    if cache_key in _OG_CACHE:
        return _OG_CACHE[cache_key]

    w, h = 1200, 630
    img = Image.new("RGB", (w, h), color=BRAND_CONFIG["colors"]["bg_dark"])
    draw = ImageDraw.Draw(img, "RGBA")

    # Gradient background glow
    draw.ellipse([900, -100, 1300, 300], fill=(0, 113, 227, 40))
    draw.ellipse([-100, 300, 400, 800], fill=(104, 52, 213, 35))

    _draw_header(draw, active_pill="ENGINEERING STUDY HUB")

    # Center hero card
    draw.rounded_rectangle([50, 135, 1150, 545], radius=24, fill="#131c31", outline="#22324f", width=1)

    f_hero = _get_font(bold=True, size=48)
    f_sub = _get_font(bold=False, size=24)
    f_badge = _get_font(bold=True, size=18)

    draw.text((90, 185), "Notes & Papers for Your College.", fill="#ffffff", font=f_hero)
    draw.text(
        (90, 255),
        "Access thousands of verified engineering PYQs, handwritten topper notes,",
        fill="#94a3b8",
        font=f_sub,
    )
    draw.text(
        (90, 290),
        "and syllabus resources. Powered by campus contributors across India.",
        fill="#94a3b8",
        font=f_sub,
    )

    # Feature badges
    features = [
        ("📄 Verified PYQs", "#1e293b", "#38bdf8"),
        ("✍ Handwritten Notes", "#1e293b", "#a855f7"),
        ("⚡ AI Exam Prep", "#1e293b", "#34d399"),
        ("💰 Earn 85% Royalties", "#1e293b", "#f59e0b"),
    ]
    cur_x = 90
    for text, bg_col, txt_col in features:
        bw = len(text) * 12 + 30
        draw.rounded_rectangle([cur_x, 380, cur_x + bw, 435], radius=14, fill=bg_col, outline="#334155")
        draw.text((cur_x + 15, 396), text, fill=txt_col, font=f_badge)
        cur_x += bw + 20

    # Student trust signal
    draw.rounded_rectangle([90, 465, 520, 515], radius=12, fill="#0f172a")
    draw.text((110, 480), "🌟 100% Student Verified  •  No Subscription Traps", fill="#38bdf8", font=f_badge)

    _draw_footer(draw)

    res = _render_image_to_bytes(img)
    _OG_CACHE[cache_key] = res
    return res


def generate_college_og(college: dict) -> bytes:
    name = str(college.get("name") or "Engineering College").strip()[:65]
    abbr = str(college.get("abbreviation") or college.get("name") or "College").strip()[:18]
    city = str(college.get("city") or "India").strip()[:25]
    files_count = str(college.get("files_count") or college.get("documents_count") or "Hundreds of")

    cache_key = f"college_og:{abbr}:{city}"
    if cache_key in _OG_CACHE:
        return _OG_CACHE[cache_key]

    w, h = 1200, 630
    img = Image.new("RGB", (w, h), color=BRAND_CONFIG["colors"]["bg_dark"])
    draw = ImageDraw.Draw(img, "RGBA")

    # Soft ambient glows
    draw.ellipse([950, -50, 1350, 350], fill=(0, 113, 227, 45))
    draw.ellipse([-50, 350, 450, 850], fill=(16, 185, 129, 35))

    _draw_header(draw, active_pill=f"{abbr} CAMPUS HUB")

    draw.rounded_rectangle([50, 135, 1150, 545], radius=24, fill="#131c31", outline="#22324f", width=1)

    # University icon / badge
    draw.rounded_rectangle([90, 170, 240, 215], radius=14, fill="#1e293b", outline="#334155")
    f_badge = _get_font(bold=True, size=16)
    draw.text((105, 182), "🏛 VERIFIED CAMPUS", fill="#10b981", font=f_badge)

    f_title = _get_font(bold=True, size=40)
    f_sub = _get_font(bold=False, size=23)
    f_stat = _get_font(bold=True, size=28)
    f_label = _get_font(bold=False, size=15)

    # College Title (wrapped)
    draw.text((90, 235), name, fill="#ffffff", font=f_title)
    draw.text((90, 295), f"Location: {city}  |  Official Academic Resource Center", fill="#94a3b8", font=f_sub)

    # Metrics container
    draw.line([(90, 355), (1110, 355)], fill="#1e293b", width=1)

    metrics = [
        ("STUDY RESOURCES", f"{files_count}+ Verified Files"),
        ("SYLLABUS COVERAGE", "B.Tech / BE All Branches"),
        ("MATERIAL TYPES", "PYQ Papers • Notes • Viva"),
    ]

    col_x = 90
    for label, val in metrics:
        draw.text((col_x, 385), label, fill="#64748b", font=f_label)
        draw.text((col_x, 415), val, fill="#38bdf8", font=f_stat)
        col_x += 345

    # Bottom Call to Action banner inside card
    draw.rounded_rectangle([90, 480, 1110, 525], radius=12, fill="#0f172a", outline="#1e293b")
    draw.text(
        (115, 493),
        "⚡ Unlock question papers, mid-sem solutions, and lab practicals for your exams.",
        fill="#ffffff",
        font=f_badge,
    )

    _draw_footer(draw)

    res = _render_image_to_bytes(img)
    _OG_CACHE[cache_key] = res
    return res


def generate_profile_og(user_data: dict) -> bytes:
    # Ensure zero privacy leakage: Only username, safe display name, college, uploads count
    username = str(user_data.get("username") or "user").strip()[:24]
    name = str(user_data.get("full_name") or user_data.get("name") or f"@{username}").strip()[:30]
    college = str(user_data.get("college") or user_data.get("college_name") or "Academic Contributor").strip()[:40]
    tier = str(user_data.get("tier") or "Verified Creator").strip().upper()[:20]
    uploads = str(user_data.get("uploads_count") or user_data.get("total_notes") or "10+")

    cache_key = f"profile_og:{username}"
    if cache_key in _OG_CACHE:
        return _OG_CACHE[cache_key]

    w, h = 1200, 630
    img = Image.new("RGB", (w, h), color=BRAND_CONFIG["colors"]["bg_dark"])
    draw = ImageDraw.Draw(img, "RGBA")

    draw.ellipse([900, -80, 1300, 320], fill=(104, 52, 213, 40))
    draw.ellipse([-50, 320, 400, 770], fill=(0, 113, 227, 35))

    _draw_header(draw, active_pill="CREATOR PROFILE")

    draw.rounded_rectangle([50, 135, 1150, 545], radius=24, fill="#131c31", outline="#22324f", width=1)

    # Avatar Circle with Initials
    avatar_size = 130
    avatar_x, avatar_y = 90, 175
    draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size], fill="#1e293b", outline="#3b82f6", width=3)
    
    initials = "".join([part[0].upper() for part in name.split()[:2]]) or "AH"
    f_avatar = _get_font(bold=True, size=52)
    draw.text((avatar_x + 30, avatar_y + 35), initials, fill="#ffffff", font=f_avatar)

    # Name & Handle
    f_name = _get_font(bold=True, size=42)
    f_handle = _get_font(bold=False, size=24)
    f_badge = _get_font(bold=True, size=16)

    draw.text((250, 185), name, fill="#ffffff", font=f_name)
    draw.text((250, 240), f"@{username}  •  {college}", fill="#94a3b8", font=f_handle)

    # Creator Tier Badge
    draw.rounded_rectangle([250, 280, 440, 318], radius=10, fill="#1e293b", outline="#334155")
    draw.text((265, 292), f"⭐ {tier}", fill="#f59e0b", font=f_badge)

    draw.line([(90, 350), (1110, 350)], fill="#1e293b", width=1)

    # Public stats only (no earnings, no email, no phone)
    f_stat_val = _get_font(bold=True, size=32)
    f_stat_lbl = _get_font(bold=False, size=16)

    stats = [
        ("CONTRIBUTIONS", f"{uploads} Materials"),
        ("COMMUNITY RATING", "4.9 / 5.0 ★"),
        ("STATUS", "Active Academic Peer"),
    ]
    cur_x = 90
    for lbl, val in stats:
        draw.text((cur_x, 380), lbl, fill="#64748b", font=f_stat_lbl)
        draw.text((cur_x, 415), val, fill="#38bdf8", font=f_stat_val)
        cur_x += 350

    draw.rounded_rectangle([90, 480, 1110, 525], radius=12, fill="#0f172a")
    draw.text((115, 493), "🎓 Explore verified notes, formula sheets, and study materials by this creator.", fill="#ffffff", font=f_badge)

    _draw_footer(draw)

    res = _render_image_to_bytes(img)
    _OG_CACHE[cache_key] = res
    return res


def generate_leaderboard_og() -> bytes:
    cache_key = "leaderboard_og"
    if cache_key in _OG_CACHE:
        return _OG_CACHE[cache_key]

    w, h = 1200, 630
    img = Image.new("RGB", (w, h), color=BRAND_CONFIG["colors"]["bg_dark"])
    draw = ImageDraw.Draw(img, "RGBA")

    draw.ellipse([900, -80, 1300, 320], fill=(245, 158, 11, 40))
    draw.ellipse([-50, 320, 400, 770], fill=(0, 113, 227, 35))

    _draw_header(draw, active_pill="CAMPUS LEADERBOARD")

    draw.rounded_rectangle([50, 135, 1150, 545], radius=24, fill="#131c31", outline="#22324f", width=1)

    f_title = _get_font(bold=True, size=46)
    f_sub = _get_font(bold=False, size=23)
    f_badge = _get_font(bold=True, size=18)

    draw.text((90, 185), "🏆 Top Campus Creators & Rankers", fill="#ffffff", font=f_title)
    draw.text((90, 250), "Recognizing student contributors uploading top-scoring notes and PYQ solutions.", fill="#94a3b8", font=f_sub)

    # Rank boxes
    ranks = [
        ("🥇 Rank 1", "Campus Champions", "#fbbf24"),
        ("🥈 Rank 2", "Distinguished Contributors", "#94a3b8"),
        ("🥉 Rank 3", "Rising Academic Creators", "#d97706"),
    ]
    cur_x = 90
    for r_title, r_desc, col in ranks:
        draw.rounded_rectangle([cur_x, 320, cur_x + 315, 440], radius=16, fill="#0f172a", outline="#1e293b")
        draw.text((cur_x + 25, 345), r_title, fill=col, font=f_title)
        draw.text((cur_x + 25, 400), r_desc, fill="#64748b", font=_get_font(bold=False, size=16))
        cur_x += 350

    draw.rounded_rectangle([90, 475, 1110, 525], radius=12, fill="#1e293b")
    draw.text((115, 490), "⚡ Upload your notes to earn score points, climb the leaderboard, and win campus rewards.", fill="#38bdf8", font=f_badge)

    _draw_footer(draw)

    res = _render_image_to_bytes(img)
    _OG_CACHE[cache_key] = res
    return res


def generate_ambassador_og() -> bytes:
    cache_key = "ambassador_og"
    if cache_key in _OG_CACHE:
        return _OG_CACHE[cache_key]

    w, h = 1200, 630
    img = Image.new("RGB", (w, h), color=BRAND_CONFIG["colors"]["bg_dark"])
    draw = ImageDraw.Draw(img, "RGBA")

    draw.ellipse([950, -50, 1350, 350], fill=(16, 185, 129, 45))
    draw.ellipse([-50, 350, 450, 850], fill=(0, 113, 227, 35))

    _draw_header(draw, active_pill="CAMPUS AMBASSADOR")

    draw.rounded_rectangle([50, 135, 1150, 545], radius=24, fill="#131c31", outline="#22324f", width=1)

    f_title = _get_font(bold=True, size=46)
    f_sub = _get_font(bold=False, size=23)
    f_badge = _get_font(bold=True, size=18)

    draw.text((90, 185), "🌱 Become an AbhiHub Campus Ambassador", fill="#ffffff", font=f_title)
    draw.text((90, 250), "Lead the academic movement at your college. Help peers find verified resources.", fill="#94a3b8", font=f_sub)

    perks = [
        ("🎓 Certificate of Leadership", "#1e293b", "#38bdf8"),
        ("💼 Exclusive Stipend & Perks", "#1e293b", "#34d399"),
        ("🚀 Direct Access to Founders", "#1e293b", "#a855f7"),
    ]
    cur_x = 90
    for p_title, bg_col, col in perks:
        bw = len(p_title) * 12 + 40
        draw.rounded_rectangle([cur_x, 340, cur_x + bw, 400], radius=14, fill=bg_col, outline="#334155")
        draw.text((cur_x + 20, 360), p_title, fill=col, font=f_badge)
        cur_x += bw + 20

    draw.rounded_rectangle([90, 465, 1110, 520], radius=14, fill="#0f172a")
    draw.text((115, 482), "✨ Applications open for B.Tech / Engineering students across all universities.", fill="#ffffff", font=f_badge)

    _draw_footer(draw)

    res = _render_image_to_bytes(img)
    _OG_CACHE[cache_key] = res
    return res


def generate_static_page_og(title: str, subtitle: str = "") -> bytes:
    clean_title = str(title or "Academic Resource").strip()[:50]
    clean_sub = str(subtitle or "Official Information and Guidelines").strip()[:80]

    cache_key = f"static_og:{clean_title}"
    if cache_key in _OG_CACHE:
        return _OG_CACHE[cache_key]

    w, h = 1200, 630
    img = Image.new("RGB", (w, h), color=BRAND_CONFIG["colors"]["bg_dark"])
    draw = ImageDraw.Draw(img, "RGBA")

    draw.ellipse([900, -80, 1300, 320], fill=(0, 113, 227, 40))

    _draw_header(draw, active_pill="INFORMATION")

    draw.rounded_rectangle([50, 135, 1150, 545], radius=24, fill="#131c31", outline="#22324f", width=1)

    f_title = _get_font(bold=True, size=50)
    f_sub = _get_font(bold=False, size=24)
    f_badge = _get_font(bold=True, size=18)

    draw.text((90, 210), clean_title, fill="#ffffff", font=f_title)
    draw.text((90, 280), clean_sub, fill="#94a3b8", font=f_sub)

    draw.line([(90, 360), (1110, 360)], fill="#1e293b", width=1)

    draw.rounded_rectangle([90, 420, 600, 480], radius=14, fill="#0f172a", outline="#1e293b")
    draw.text((115, 442), "🛡 Verified Platform  •  Proudly Made in India", fill="#38bdf8", font=f_badge)

    _draw_footer(draw)

    res = _render_image_to_bytes(img)
    _OG_CACHE[cache_key] = res
    return res


def generate_default_og() -> bytes:
    return generate_home_og()
