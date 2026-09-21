import requests
import os
import logging

def submit_to_indexnow(url_list):
    """
    Submits a list of URLs to Bing IndexNow for faster indexing.
    """
    key = os.getenv('INDEX_NOW_BING_API_KEY', '').strip()
    host = os.getenv('BASE_DOMAIN', 'www.abhihub.edu.eu.org').strip().lower()
    if not key:
        logging.error("IndexNow is not configured: INDEX_NOW_BING_API_KEY is missing.")
        return False
    
    payload = {
        "host": host,
        "key": key,
        "keyLocation": f"https://{host}/{key}.txt",
        "urlList": url_list
    }
    
    try:
        response = requests.post(
            "https://api.indexnow.org/indexnow",
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10,
        )
        if response.status_code in (200, 202):
            logging.info(f"Successfully submitted {len(url_list)} URLs to IndexNow.")
        else:
            logging.warning(f"IndexNow submission failed: {response.status_code} - {response.text}")
        return response.status_code in (200, 202)
    except requests.RequestException as e:
        logging.error(f"Error submitting to IndexNow: {e}")
        return False


def is_resource_indexable(doc: dict) -> bool:
    """
    Uniform quality gate for indexing resource URLs (meta robots + sitemap).
    A resource is indexable only if:
    1. It has an active/approved file URL.
    2. Title length is >= 5 characters.
    3. Has either a meaningful description (>= 50 words) OR an extracted PDF text preview (>= 30 words).
    """
    if not isinstance(doc, dict):
        return False
    if not doc.get('file_url'):
        return False
    
    status = doc.get('status')
    if status and str(status).lower() not in ('approved', 'active', 'published'):
        return False
        
    title = str(doc.get('title') or '').strip()
    if len(title) < 5:
        return False
        
    raw_desc = str(doc.get('description') or '').strip()
    desc_text = raw_desc
    if raw_desc.startswith('{') and raw_desc.endswith('}'):
        try:
            import json
            d_obj = json.loads(raw_desc)
            desc_text = d_obj.get('user_description') or d_obj.get('summary') or ''
        except Exception:
            pass
            
    desc_words = len(desc_text.split())
    preview_text = str(doc.get('extracted_text_preview') or doc.get('preview_text') or '').strip()
    preview_words = len(preview_text.split())
    
    return desc_words >= 50 or preview_words >= 30

