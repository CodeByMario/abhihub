"""
services/doc_scanner.py - Document Scanner, Deskew, Shadow Removal, Book-Mode Merge & Image Watermark

Handles:
1. Deskewing via Hough line / projection variance text-line tilt detection.
2. Background illumination normalization & shadow removal (scanned book effect).
3. Two-sided paper book-mode merge: stitches front & back side side-by-side on single landscape page.
4. Logo image watermarking with alpha blending in bottom-right corner.
5. High-efficiency JPEG & PDF compression.
"""

import os
import io
import logging
import cv2
import numpy as np
from PIL import Image

DEFAULT_WATERMARK_PATHS = [
    os.path.join("static", "images", "logo.png"),
    os.path.join("static", "premium", "images", "logo.png"),
    os.path.join("static", "images", "default_logo.png")
]


# =============================================================== 1. Deskew
def estimate_skew_angle(image: np.ndarray, max_angle: float = 15.0) -> float:
    """Find text-line tilt in degrees using projection profile variance."""
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        scale = 1000.0 / max(gray.shape)
        if scale < 1.0:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        bw = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15
        )
        h, w = bw.shape
        center = (w // 2, h // 2)

        def score(angle):
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            r = cv2.warpAffine(bw, M, (w, h), flags=cv2.INTER_NEAREST)
            return np.var(r.sum(axis=1).astype(np.float64))

        coarse = np.arange(-max_angle, max_angle + 0.01, 1.0)
        a0 = coarse[int(np.argmax([score(a) for a in coarse]))]
        fine = np.arange(a0 - 1.0, a0 + 1.01, 0.1)
        return float(fine[int(np.argmax([score(a) for a in fine]))])
    except Exception as e:
        logging.debug(f"[doc_scanner] Skew estimation fallback: {e}")
        return 0.0


def rotate_bound(image: np.ndarray, angle: float, border=(255, 255, 255)) -> np.ndarray:
    """Rotate image without cropping edges; background filled white."""
    h, w = image.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += nw / 2 - w / 2
    M[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(
        image, M, (nw, nh), flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=border
    )


# =============================================================== 2. Enhancement
def remove_shadows(gray: np.ndarray) -> np.ndarray:
    """Eliminate uneven camera shadows and page wrinkles via morphological background division."""
    k = (max(gray.shape) // 30) | 1
    k = max(7, min(k, 51))
    bg = cv2.medianBlur(cv2.dilate(gray, np.ones((7, 7), np.uint8)), k)
    norm = cv2.divide(gray, bg, scale=255)
    return cv2.normalize(norm, None, 0, 255, cv2.NORM_MINMAX)


def enhance(image: np.ndarray, mode: str = "gray", upscale: float = 1.0) -> np.ndarray:
    """Professional document scanner enhancement (shadow removal + unsharp mask)."""
    if upscale and upscale != 1.0:
        image = cv2.resize(image, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)

    if mode == "color":
        out = cv2.merge([remove_shadows(c) for c in cv2.split(image)])
        out = cv2.fastNlMeansDenoisingColored(out, None, 5, 5, 7, 21)
    else:
        gray_input = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        out = remove_shadows(gray_input)
        out = cv2.fastNlMeansDenoising(out, None, h=7)

    blur = cv2.GaussianBlur(out, (0, 0), 2)
    out = cv2.addWeighted(out, 1.6, blur, -0.6, 0)
    out = np.clip((out.astype(np.float32) - 50) * (255.0 / (220 - 50)), 0, 255).astype(np.uint8)

    if mode == "bw":
        _, out = cv2.threshold(out, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    if out.ndim == 2:
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    return out


# =============================================================== 3. Watermark
def _load_watermark_rgba(watermark_path: str = None) -> np.ndarray:
    """Return an RGBA watermark from an image file path or text fallback."""
    candidate_paths = [watermark_path] if watermark_path else []
    candidate_paths.extend(DEFAULT_WATERMARK_PATHS)

    for p in candidate_paths:
        if p and os.path.isfile(p):
            wm = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            if wm is not None:
                if wm.ndim == 2:
                    wm = cv2.cvtColor(wm, cv2.COLOR_GRAY2BGR)
                if wm.shape[2] == 3:
                    # Treat pure/near white as transparent
                    g = cv2.cvtColor(wm, cv2.COLOR_BGR2GRAY)
                    alpha = np.clip((255 - g).astype(np.float32) * 2.0, 0, 255).astype(np.uint8)
                    wm = np.dstack([wm, alpha])
                return wm

    # Fallback to high-res brand text canvas
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale, thick = 2.0, 4
    text = "AbhiHub"
    (tw, th), base = cv2.getTextSize(text, font, scale, thick)
    canvas = np.zeros((th + base + 20, tw + 20, 4), np.uint8)
    cv2.putText(canvas, text, (10, th + 10), font, scale, (90, 90, 90, 255), thick, cv2.LINE_AA)
    return canvas


def add_watermark(image: np.ndarray, watermark_path: str = None, opacity: float = 0.40,
                  scale: float = 0.15, margin: float = 0.02) -> np.ndarray:
    """Blend brand image watermark into the bottom-right corner."""
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    H, W = image.shape[:2]
    wm = _load_watermark_rgba(watermark_path)
    if wm is None:
        return image

    new_w = max(24, int(W * scale))
    new_h = int(wm.shape[0] * new_w / wm.shape[1])
    max_h = int(H * 0.18)
    if new_h > max_h:
        new_h = max_h
        new_w = int(wm.shape[1] * new_h / wm.shape[0])

    wm = cv2.resize(wm, (new_w, new_h), interpolation=cv2.INTER_AREA)

    m = int(min(W, H) * margin)
    x2, y2 = W - m, H - m
    x1, y1 = x2 - new_w, y2 - new_h
    if x1 < 0 or y1 < 0:
        return image

    alpha = (wm[:, :, 3:4].astype(np.float32) / 255.0) * opacity
    roi = image[y1:y2, x1:x2].astype(np.float32)
    blended = roi * (1.0 - alpha) + wm[:, :, :3].astype(np.float32) * alpha
    image[y1:y2, x1:x2] = np.clip(blended, 0, 255).astype(np.uint8)
    return image


# =============================================================== 4. Book Merge (Side-by-Side Landscape)
def merge_pages_side_by_side(front_img: np.ndarray, back_img: np.ndarray,
                             gutter_px: int = 16, border_color=(255, 255, 255)) -> np.ndarray:
    """
    Merge front side and back side images side-by-side like an open book on a single landscape page.
    Guarantees NO overlapping.
    Left: Front page (Page 1)
    Right: Back page (Page 2)
    """
    h1, w1 = front_img.shape[:2]
    h2, w2 = back_img.shape[:2]

    # Normalize to uniform height
    target_h = max(h1, h2)
    w1_scaled = int(w1 * target_h / h1)
    front_scaled = cv2.resize(front_img, (w1_scaled, target_h), interpolation=cv2.INTER_AREA)

    w2_scaled = int(w2 * target_h / h2)
    back_scaled = cv2.resize(back_img, (w2_scaled, target_h), interpolation=cv2.INTER_AREA)

    total_w = w1_scaled + gutter_px + w2_scaled
    canvas = np.full((target_h, total_w, 3), border_color[0], dtype=np.uint8)

    # Place front page on left
    canvas[0:target_h, 0:w1_scaled] = front_scaled

    # Place subtle vertical book crease line in gutter
    crease_x = w1_scaled + (gutter_px // 2)
    canvas[0:target_h, crease_x:crease_x + 1] = (220, 225, 230)

    # Place back page on right
    canvas[0:target_h, w1_scaled + gutter_px:total_w] = back_scaled
    return canvas


# =============================================================== 5. Compression & Main Pipeline
def compress_image(img: np.ndarray, quality: int = 82, max_width: int = 2400,
                   target_kb: int = None) -> (bytes, np.ndarray):
    """Downscale to max_width and JPEG-encode; optionally fit under target_kb."""
    h, w = img.shape[:2]
    if max_width and w > max_width:
        img = cv2.resize(img, (max_width, int(h * max_width / w)), interpolation=cv2.INTER_AREA)

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(quality), cv2.IMWRITE_JPEG_OPTIMIZE, 1])
    data = buf.tobytes()

    if target_kb:
        limit = target_kb * 1024
        q = quality
        while len(data) > limit and q > 25:
            q -= 5
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(q), cv2.IMWRITE_JPEG_OPTIMIZE, 1])
            data = buf.tobytes()
    return data, img


def process_paper_scan(front_bytes: bytes, back_bytes: bytes = None,
                       is_two_sided: bool = False, mode: str = "gray",
                       watermark_path: str = None, quality: int = 82,
                       no_deskew: bool = False) -> bytes:
    """
    Complete scanning pipeline:
    1. Read front (and optional back) images.
    2. Estimate skew and deskew without edge cutoff.
    3. Remove shadows and enhance contrast.
    4. If two-sided: merge side-by-side like an open book (landscape, zero overlap).
    5. Add image logo watermark to bottom-right corner.
    6. Compress to optimized JPEG bytes.
    """
    nparr_front = np.frombuffer(front_bytes, np.uint8)
    front_img = cv2.imdecode(nparr_front, cv2.IMREAD_COLOR)
    if front_img is None:
        return front_bytes

    # 1. Process Front Page
    if not no_deskew:
        angle_front = estimate_skew_angle(front_img)
        if abs(angle_front) > 0.2:
            front_img = rotate_bound(front_img, angle_front)
    front_enhanced = enhance(front_img, mode=mode)

    final_img = front_enhanced

    # 2. Process Back Page & Merge Side-by-Side if provided
    if is_two_sided and back_bytes:
        nparr_back = np.frombuffer(back_bytes, np.uint8)
        back_img = cv2.imdecode(nparr_back, cv2.IMREAD_COLOR)
        if back_img is not None:
            if not no_deskew:
                angle_back = estimate_skew_angle(back_img)
                if abs(angle_back) > 0.2:
                    back_img = rotate_bound(back_img, angle_back)
            back_enhanced = enhance(back_img, mode=mode)

            # Merge both pages side-by-side (Book Mode)
            final_img = merge_pages_side_by_side(front_enhanced, back_enhanced, gutter_px=16)

    # 3. Apply Brand Logo Image Watermark (bottom-right)
    final_img = add_watermark(final_img, watermark_path=watermark_path)

    # 4. Compress to optimized JPEG bytes
    data, _ = compress_image(final_img, quality=quality, max_width=2400)
    return data
