import os
from app import app

client = app.test_client()
print("--- TEST /api/report-suspect ---")
res = client.post('/api/report-suspect', json={'action': 'test'})
print("STATUS:", res.status_code)
print("BODY:", res.get_data(as_text=True))

print("--- TEST /rank ---")
res2 = client.get('/rank')
print("STATUS:", res2.status_code)
print("BODY:", res2.get_data(as_text=True))
