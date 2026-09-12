"""
know_me_generator.py — Word cloud + Signature wall generator
Uses: Pillow (already in requirements), wordcloud (to be added)
"""

import os
import io
import logging
from typing import List

# Static output dir
GENERATED_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "know_me", "generated")
os.makedirs(GENERATED_DIR, exist_ok=True)


def generate_wordcloud(word_list: List[str], wall_id: str) -> str:
    """
    Generate a word cloud PNG from a list of words.
    Returns: local file path (relative to static/) or empty string on failure.
    """
    try:
        from wordcloud import WordCloud

        if not word_list:
            return ""

        text = " ".join(word_list)
        wc = WordCloud(
            width=900,
            height=500,
            background_color="#0f172a",
            colormap="cool",
            max_words=80,
            prefer_horizontal=0.85,
            min_font_size=14,
            max_font_size=100,
            collocations=False,
        ).generate(text)

        filename = f"wc_{wall_id}.png"
        out_path = os.path.join(GENERATED_DIR, filename)
        wc.to_file(out_path)
        logging.info(f"[Generator] Word cloud saved: {out_path}")
        return f"know_me/generated/{filename}"
    except ImportError:
        logging.warning("[Generator] wordcloud not installed — skipping word cloud")
        return ""
    except Exception as e:
        logging.error(f"[Generator] generate_wordcloud error: {e}")
        return ""


def generate_signature_wall(signature_urls: List[str], wall_id: str) -> str:
    """
    Download signature images and composite them into a wall PNG.
    Returns: local file path (relative to static/) or empty string on failure.
    """
    try:
        from PIL import Image
        import requests as req

        if not signature_urls:
            return ""

        sigs = []
        for url in signature_urls[:30]:  # Cap at 30 signatures
            try:
                r = req.get(url, timeout=5)
                if r.status_code == 200:
                    img = Image.open(io.BytesIO(r.content)).convert("RGBA")
                    sigs.append(img)
            except Exception:
                continue

        if not sigs:
            return ""

        # Layout: up to 5 per row, 160px wide each, 90px tall
        cols = 5
        thumb_w, thumb_h = 160, 90
        rows = (len(sigs) + cols - 1) // cols
        canvas = Image.new("RGB", (cols * thumb_w, rows * thumb_h), (15, 23, 42))

        for i, sig in enumerate(sigs):
            sig.thumbnail((thumb_w, thumb_h))
            bg = Image.new("RGB", (thumb_w, thumb_h), (15, 23, 42))
            offset = ((thumb_w - sig.width) // 2, (thumb_h - sig.height) // 2)
            bg.paste(sig, offset, sig if sig.mode == "RGBA" else None)
            x = (i % cols) * thumb_w
            y = (i // cols) * thumb_h
            canvas.paste(bg, (x, y))

        filename = f"sw_{wall_id}.png"
        out_path = os.path.join(GENERATED_DIR, filename)
        canvas.save(out_path, "PNG", optimize=True)
        logging.info(f"[Generator] Signature wall saved: {out_path}")
        return f"know_me/generated/{filename}"
    except Exception as e:
        logging.error(f"[Generator] generate_signature_wall error: {e}")
        return ""


def upload_to_firebase(local_static_path: str, firebase_path: str) -> str:
    """
    Upload a generated asset to Firebase Storage.
    Returns: public download URL or empty string.
    local_static_path: path relative to static/ e.g. 'know_me/generated/wc_xxx.png'
    """
    try:
        from firebase_admin import storage as fb_storage
        abs_path = os.path.join(
            os.path.dirname(__file__), "..", "static", local_static_path
        )
        bucket = fb_storage.bucket()
        blob = bucket.blob(firebase_path)
        blob.upload_from_filename(abs_path, content_type="image/png")
        blob.make_public()
        url = blob.public_url
        logging.info(f"[Generator] Uploaded to Firebase: {firebase_path} → {url}")
        return url
    except Exception as e:
        logging.error(f"[Generator] upload_to_firebase error: {e}")
        return ""
