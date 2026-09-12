import requests
import os
import logging

def submit_to_indexnow(url_list):
    """
    Submits a list of URLs to Bing IndexNow for faster indexing.
    """
    key = os.getenv('INDEX_NOW_BING_API_KEY', '').strip()
    host = os.getenv('BASE_DOMAIN', 'app.abhihub.run.place').strip().lower()
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
