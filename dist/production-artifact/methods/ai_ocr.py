"""
ai_ocr.py — Free image-to-text OCR, transcription repair, and Supabase caching.
"""
from __future__ import annotations

import base64
import logging
import os
import requests

log = logging.getLogger(__name__)


def convert_image_to_text(file_url: str) -> str:
    """Download image, call Gemini Vision to transcribe & fix OCR errors, return clean text."""
    gemini_key = os.getenv("GEMINI_API", "").strip().strip("'\"") or os.getenv("GEMINI_API_KEY", "").strip().strip("'\"")
    if not gemini_key or not file_url:
        return ""
    try:
        resp = requests.get(file_url, timeout=15, headers={"User-Agent": "AbhiHub-OCR/1.0"})
        if not resp.ok:
            return ""

        content_type = resp.headers.get("Content-Type", "image/jpeg").lower()
        if ";" in content_type:
            content_type = content_type.split(";")[0]
        if not content_type.startswith("image/"):
            content_type = "image/jpeg"

        b64 = base64.b64encode(resp.content).decode("ascii")
        prompt = (
            "Transcribe all text from this study/exam image verbatim. "
            "Correct OCR errors, broken words, missing punctuation, and irregular spacing. "
            "Format mathematical equations and formulas in clean LaTeX ($...$ or $$...$$). "
            "Return ONLY the cleaned transcribed text."
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={gemini_key}"
        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": content_type, "data": b64}}
                ]
            }],
            "generationConfig": {
                "maxOutputTokens": 2048,
                "temperature": 0.1
            }
        }
        res = requests.post(url, json=payload, timeout=25)
        if not res.ok:
            log.warning(f"[ai_ocr] Gemini API responded with HTTP {res.status_code}")
            return ""

        data = res.json()
        candidates = data.get("candidates") or []
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts).strip()
    except Exception as e:
        log.warning(f"[ai_ocr] convert_image_to_text error: {e}")
    return ""


def get_or_create_image_alt(doc_id: str | None, file_url: str, doc_meta: dict | None = None) -> str:
    """Check Supabase for cached image_alt. If missing, transcribe via AI and persist."""
    from methods.supabase_helper import init_supabase

    meta = doc_meta or {}
    cached_alt = (meta.get("image_alt") or "").strip()
    if cached_alt:
        return cached_alt

    client = init_supabase()
    if client and doc_id:
        try:
            r = client.table("documents").select("image_alt").eq("id", str(doc_id)).limit(1).execute()
            if r.data and (r.data[0].get("image_alt") or "").strip():
                return r.data[0]["image_alt"].strip()
        except Exception:
            pass

    # No alt cached -> Convert image into text via Gemini Free Vision
    cleaned_text = convert_image_to_text(file_url)
    if cleaned_text and client and doc_id:
        try:
            client.table("documents").update({"image_alt": cleaned_text}).eq("id", str(doc_id)).execute()
            log.info(f"[ai_ocr] Saved new image_alt for doc {doc_id} to Supabase")
        except Exception as err:
            log.warning(f"[ai_ocr] Failed updating image_alt in Supabase: {err}")

    return cleaned_text or ""
