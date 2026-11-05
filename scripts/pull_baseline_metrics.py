import json, os
from data.db import get_client

client = get_client()

# 1. Total Profiles / Users
profiles_res = client.table("profiles").select("id, college_id", count="exact").execute()
total_users = profiles_res.count if hasattr(profiles_res, "count") and profiles_res.count is not None else len(profiles_res.data or [])

# 2. Uploaders & Pricers
docs_res = client.table("documents").select("id, uploader_id, seller_id, is_paid, price").execute()
docs = docs_res.data or []

uploaders = set(d.get("uploader_id") for d in docs if d.get("uploader_id"))
pricers = set(
    (d.get("seller_id") or d.get("uploader_id"))
    for d in docs
    if (d.get("is_paid") is True or float(d.get("price") or 0) > 0) and (d.get("seller_id") or d.get("uploader_id"))
)

# 3. Sales
tx_path = os.path.join(os.path.dirname(__file__), "..", "data", "payment_transactions.json")
completed_sales = 0
unique_sellers_with_sales = set()

if os.path.exists(tx_path):
    try:
        with open(tx_path, "r", encoding="utf-8") as f:
            txs = json.load(f)
            for _, tx in txs.items():
                if tx.get("status") == "completed" and tx.get("doc_id"):
                    completed_sales += 1
    except Exception:
        pass

print("=== BASELINE NUMBERS ===")
print(f"Total Users Registered : {total_users}")
print(f"Users Who Uploaded     : {len(uploaders)}")
print(f"Users Who Priced a File: {len(pricers)}")
print(f"Total File Sales Made  : {completed_sales}")
