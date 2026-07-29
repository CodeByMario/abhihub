import requests
import os
import logging

def submit_to_indexnow(url_list):
    """
    Submits a list of URLs to Bing IndexNow for faster indexing.
    """
    key = os.getenv('INDEX_NOW_BING_API_KEY', '31d61c30c86d4fc7a7bb3584a4d225c9').strip()
    host = "app.abhihub.run.place" 
    
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
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        if response.status_code == 200:
            logging.info(f"Successfully submitted {len(url_list)} URLs to IndexNow.")
        else:
            logging.warning(f"IndexNow submission failed: {response.status_code} - {response.text}")
        return response.status_code == 200
    except Exception as e:
        logging.error(f"Error submitting to IndexNow: {e}")
        return False
