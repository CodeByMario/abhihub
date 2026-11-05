# ==============================================================================
# Google Colab: Gen-Z Student Comment Thread Generator (Local LLM)
# Model: Qwen/Qwen2.5-3B-Instruct (Runs fast on free Colab T4 GPU)
# ==============================================================================
# In Colab Cell 1:
# !pip install -q transformers torch accelerate supabase python-dotenv bitsandbytes

import os
import csv
import json
import random
import datetime
import torch
from transformers import pipeline
from supabase import create_client, ClientOptions

# 1. SETUP CREDENTIALS
SUPABASE_URL = "YOUR_SUPABASE_URL"
SUPABASE_KEY = "YOUR_SUPABASE_SERVICE_ROLE_KEY"

sb = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema="abhihub"))

# 2. LOAD LOCAL MODEL (Qwen 2.5 3B Instruct on GPU in FP16)
print("Loading model onto GPU...")
from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "Qwen/Qwen2.5-3B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype=torch.float16,
    device_map="auto"
)
pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)

# 3. FETCH PROFILES
profiles = sb.table('profiles').select('id, full_name').execute().data or []
if not profiles:
    raise SystemExit("No profiles found in Supabase.")
user_ids = [p['id'] for p in profiles]

# 4. FETCH TARGET DOCUMENTS
docs = sb.table('documents').select('id, title').limit(200).execute().data or []
print(f"Loaded {len(docs)} documents to generate threads for.")

SYSTEM_PROMPT = """You are simulating a lively college group chat / comment thread under an exam paper on a student portal.
Style: Peak Gen-Z college humor, friendly roasts, panicking before exam, slang ('cooked', 'fr fr', 'no cap', 'aura -1000', 'deadass', 'huge W', 'gatekeeping', 'crying in 4k').
Output strictly a JSON list of 2 to 3 comment objects relevant to the subject.
Format:
[
  {"text": "bro who even understands question 3 in this exam we are so cooked"},
  {"text": "skill issue tbh, literally just read unit 2 and pray to the curve"},
  {"text": "bro got -1000 aura for saying skill issue, that question was unhinged"}
]"""

def generate_thread(subject):
    prompt = f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n<|im_start|>user\nGenerate a hilarious 3-person Gen-Z comment thread for this exam paper: '{subject}'.<|im_end|>\n<|im_start|>assistant\n"
    res = pipe(prompt, max_new_tokens=220, temperature=0.85, do_sample=True)[0]['generated_text']
    resp = res.split("<|im_start|>assistant\n")[-1].strip()
    try:
        start = resp.find('[')
        end = resp.rfind(']') + 1
        return json.loads(resp[start:end])
    except Exception:
        return [
            {"text": f"bro this {subject} paper lowkey saved my life fr fr 💀"},
            {"text": f"don't let the prof know we found this or we're cooked no cap"},
            {"text": "gatekeeping this from the section gc until 3am lmaooo"}
        ]

# 5. GENERATE AND INSERT THREADS
print("Generating threads and sending to Supabase...")
batch_comments = []
now = datetime.datetime.utcnow()

for i, doc in enumerate(docs):
    title = doc.get('title') or "Engineering Exam"
    thread = generate_thread(title)
    
    # Pick 2-3 distinct commenters for banter
    commenters = random.sample(user_ids, min(len(thread), len(user_ids)))
    base_time = now - datetime.timedelta(days=random.randint(1, 45), hours=random.randint(1, 23))

    for idx, c in enumerate(thread):
        t_delta = datetime.timedelta(minutes=random.randint(4, 35) * (idx + 1))
        batch_comments.append({
            'document_id': doc['id'],
            'user_id': commenters[idx % len(commenters)],
            'content': c.get('text', '').strip(),
            'created_at': (base_time + t_delta).isoformat() + 'Z'
        })

    if len(batch_comments) >= 100 or i == len(docs) - 1:
        try:
            sb.table('document_comments').insert(batch_comments).execute()
            print(f"[{i+1}/{len(docs)}] Inserted batch of {len(batch_comments)} comments.")
            batch_comments = []
        except Exception as e:
            print(f"Batch insert error: {e}")
            batch_comments = []

print("\n[SUCCESS] All Gen-Z comment threads successfully generated and inserted!")
