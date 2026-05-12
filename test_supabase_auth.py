import os
import requests
from dotenv import load_dotenv

load_dotenv('.env')
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY").strip("'").strip('"')

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
    "Accept-Profile": "abhihub"
}

res = requests.get(f"{url}/rest/v1/documents?select=count&limit=1", headers=headers)
print(res.status_code)
print(res.text)
