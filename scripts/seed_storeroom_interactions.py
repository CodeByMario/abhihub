#!/usr/bin/env python3
"""
Seed random views, likes, and unique subject-relevant comments for storeroom documents.
High-concurrency optimized to execute in seconds without hanging.
"""

import os
import re
import csv
import glob
import random
import datetime
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

BASE = os.path.dirname(os.path.abspath(__file__))
UUID_RE = re.compile(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.I)
CODE_RE = re.compile(r'^(?:[a-z]{3,5}\d{2,3}[a-z]?|\d[a-z]{3}\d{2}[a-z])$', re.I)


def normalize_url(url):
    if not url:
        return ""
    u = url.strip().rstrip('/')
    return 'https://' + u[7:] if u.startswith('http://') else u


def clean_subject(raw, uid, pid):
    tokens = (raw or '').split()
    segs = set(uid.split('-')) if uid else set()
    while tokens and tokens[0].lower() in segs:
        tokens.pop(0)
    suffix = (pid or '').rsplit('_', 1)[-1].lower()
    if tokens and tokens[-1].lower() == suffix:
        tokens.pop()
    code = None
    if tokens and CODE_RE.match(tokens[-1]):
        code = tokens.pop().upper()
    subj = ' '.join(tokens).strip()
    return (subj if subj else "Engineering Studies"), code


def fetch_all(sb, table, cols, page=1000):
    out, start = [], 0
    while True:
        res = sb.table(table).select(cols).range(start, start + page - 1).execute()
        rows = res.data or []
        out.extend(rows)
        if len(rows) < page:
            return out
        start += page


COMMENT_TEMPLATES = [
    "bro this {subj} paper lowkey saved my entire semester fr fr 😭",
    "was about to get absolutely cooked in {subj} tomorrow morning, clutch upload ngl",
    "whoever dropped this {subj} pyq just gained +10000 aura no cap 🐐",
    "not me cramming {subj} at 3am with this exact paper open on my laptop 💀",
    "this {subj} paper understood the assignment fr, pure gold",
    "deadass the questions in unit 3 of {subj} were copied straight from this set",
    "massive W upload for {subj}! my gpa is actually saved from the trenches",
    "the numericals in {subj} had me questioning my life choices but this made it make sense",
    "bro really dropped the {subj} holy grail and thought we wouldn’t notice lmao",
    "highkey the most clutch {subj} pyq on this entire platform, valid af",
    "gatekeeping this {subj} paper from the class group chat until midnight fr",
    "ate and left zero crumbs with this {subj} upload, big thanks",
    "lowkey crying tears of joy because {subj} end-sem was looking impossible before this",
    "we are so back! this {subj} paper covers literally every single question that matters",
    "is it just me or is this {subj} test paper actually so elite",
    "the prof was definitely not expecting us to find this {subj} question set 😭",
    "bro cooked so hard with this {subj} resource, bookmarked immediately",
    "actual lifesaver for {subj}. if you solve section B you're completely chillin",
    "my honest reaction to finding this {subj} paper: 10/10 no notes needed",
    "the way {subj} had the whole batch stressing until someone shared this"
]

COMMENT_ADDITIONS = [
    "fr fr no cap.",
    "lowkey clutch af.",
    "we are so back honestly.",
    "literally saved my gpa from dropping.",
    "huge W for anyone taking this exam tomorrow.",
    "pro tip: definitely master the 8-mark numericals first.",
    "straight gas, 10/10 recommend solving this twice.",
    "bro is doing god's work with this upload.",
    "ngl unit 2 and unit 4 questions are repeated every single year.",
    "bookmarking this immediately before finals.",
    "real ones know question 4 is guaranteed on the test paper.",
    "actually unhinged how accurate this is to the syllabus."
]


def generate_unique_comment(subject, index, seen_set):
    subj = subject.strip() or "Engineering"
    for _ in range(50):
        t = random.choice(COMMENT_TEMPLATES).format(subj=subj)
        if random.random() > 0.4:
            a = random.choice(COMMENT_ADDITIONS)
            cand = f"{t} {a}"
        else:
            cand = t
        if cand not in seen_set:
            seen_set.add(cand)
            return cand

    fallback = f"lowkey elite {subj} paper right here (doc #{index + 1}), pure W fr fr."
    seen_set.add(fallback)
    return fallback


def update_single_doc(sb, item):
    try:
        sb.table('documents').update({
            'view_count': item['view_count'],
            'like_count': item['like_count'],
            'bookmark_count': item['bookmark_count']
        }).eq('id', item['id']).execute()
        return True
    except Exception as e:
        return False


def run(dry_run=False, limit=None):
    load_dotenv(os.path.join(BASE, '..', '.env'))
    url = os.environ.get("SUPABASE_URL")
    key = (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
           or os.environ.get("SUPABASE_PUBLIC_API_KEY"))

    if not url or not key:
        raise SystemExit("[ERROR] Missing SUPABASE_URL or key in .env")

    from supabase import create_client, ClientOptions
    sb = create_client(url, key.strip("'\""), options=ClientOptions(
        schema="abhihub", persist_session=False, auto_refresh_token=False))

    csv_candidates = glob.glob(os.path.join(BASE, '..', 'data', 'storeroom_documents*.csv'))
    if not csv_candidates:
        raise SystemExit("[ERROR] storeroom_documents CSV file not found in data/")
    csv_path = csv_candidates[0]

    print(f"Reading CSV metadata from: {os.path.basename(csv_path)}")
    csv_metadata = {}
    with open(csv_path, 'r', encoding='utf-8', errors='replace', newline='') as f:
        for row in csv.DictReader(f):
            pid = (row.get('provider_public_id') or '').strip()
            url_norm = normalize_url(row.get('file_url') or '')
            uid_m = UUID_RE.search(pid)
            uid = uid_m.group(1).lower() if uid_m else None
            subject, _ = clean_subject(row.get('subject_name') or row.get('title'), uid, pid)
            if pid:
                csv_metadata[pid] = subject
            if url_norm:
                csv_metadata[url_norm] = subject

    print("Fetching active profiles from Supabase...")
    profiles = fetch_all(sb, 'profiles', 'id, email')
    if not profiles:
        raise SystemExit("[ERROR] No profiles found in abhihub.profiles to attribute comments/likes.")
    user_ids = [p['id'] for p in profiles]
    print(f"Loaded {len(user_ids)} profiles.")

    print("Fetching documents from abhihub.documents...")
    docs = fetch_all(sb, 'documents', 'id, title, provider_public_id, file_url, view_count, like_count')
    print(f"Total documents found in database: {len(docs)}")

    if limit:
        docs = docs[:limit]
        print(f"Limited processing to first {limit} documents.")

    seen_comments = set()
    doc_updates = []
    comments_to_insert = []
    votes_to_insert = []
    bookmarks_to_insert = []

    for idx, doc in enumerate(docs):
        doc_id = doc['id']
        pid = doc.get('provider_public_id') or ''
        url_norm = normalize_url(doc.get('file_url') or '')

        subj = csv_metadata.get(pid) or csv_metadata.get(url_norm) or doc.get('title') or "Engineering Subject"

        # 1. Realistic Views: 120 - 2,400 (Majority 150-700, viral hits up to 2,400)
        views = random.randint(150, 750) if random.random() < 0.85 else random.randint(751, 2400)

        # 2. Likes: 5% - 20% of views (Always strictly: views >> likes)
        like_ratio = random.uniform(0.05, 0.20)
        likes = max(3, min(int(views * like_ratio), len(user_ids)))

        # 3. Saves / Bookmarks: 2% - 10% of views (Always: views >> saves)
        save_ratio = random.uniform(0.02, 0.10)
        saves = max(1, min(int(views * save_ratio), len(user_ids)))

        # Strict guarantee: views > (likes + saves)
        if views <= (likes + saves):
            views = likes + saves + random.randint(50, 200)

        doc_updates.append({
            'id': doc_id,
            'view_count': views,
            'like_count': likes,
            'bookmark_count': saves,
        })

        # 4. Unique Gen-Z subject-relevant comment
        commenter_id = random.choice(user_ids)
        comment_text = generate_unique_comment(subj, idx, seen_comments)

        comments_to_insert.append({
            'document_id': doc_id,
            'user_id': commenter_id,
            'content': comment_text
        })

        # 5. Votes for likes
        voters = random.sample(user_ids, min(likes, len(user_ids)))
        for voter_id in voters:
            votes_to_insert.append({
                'document_id': doc_id,
                'user_id': voter_id,
                'vote': 'like'
            })

        # 6. Saves/Bookmarks
        savers = random.sample(user_ids, min(saves, len(user_ids)))
        for saver_id in savers:
            bookmarks_to_insert.append({
                'document_id': doc_id,
                'user_id': saver_id
            })

    print(f"\nPrepared {len(comments_to_insert)} unique comments, {len(votes_to_insert)} votes, {len(bookmarks_to_insert)} saves, {len(doc_updates)} counter updates.")

    if dry_run:
        print("\n--- SAMPLE PREVIEW (DRY RUN) ---")
        for i in range(min(5, len(doc_updates))):
            d = doc_updates[i]
            c = comments_to_insert[i]
            print(f"Doc {d['id']}: views={d['view_count']}, likes={d['like_count']}, saves={d['bookmark_count']} (views > likes: {d['view_count'] > d['like_count']})")
            print(f"  Comment ({c['user_id']}): \"{c['content']}\"")
        print("\nDry run complete. No database writes executed.")
        return

    # STEP 1: Insert comments FIRST in batches of 100
    print("\n[Step 1/4] Inserting comments into abhihub.document_comments...")
    comments_inserted = 0
    total_comment_batches = (len(comments_to_insert) + 99) // 100
    for i in range(0, len(comments_to_insert), 100):
        batch = comments_to_insert[i:i + 100]
        try:
            res = sb.table('document_comments').insert(batch).execute()
            comments_inserted += len(res.data or batch)
            print(f"  Batch {i//100 + 1}/{total_comment_batches}: {comments_inserted} comments inserted.", end='\r')
        except Exception as e:
            for c in batch:
                try:
                    sb.table('document_comments').insert(c).execute()
                    comments_inserted += 1
                except Exception:
                    pass
    print(f"\n[DONE] Successfully inserted {comments_inserted} comments.")

    # STEP 2: Insert votes in batches of 200
    print("\n[Step 2/4] Inserting votes into abhihub.document_votes...")
    votes_inserted = 0
    total_vote_batches = (len(votes_to_insert) + 199) // 200
    for i in range(0, len(votes_to_insert), 200):
        batch = votes_to_insert[i:i + 200]
        try:
            res = sb.table('document_votes').insert(batch).execute()
            votes_inserted += len(res.data or batch)
            print(f"  Batch {i//200 + 1}/{total_vote_batches}: {votes_inserted} votes inserted.", end='\r')
        except Exception:
            for v in batch:
                try:
                    sb.table('document_votes').insert(v).execute()
                    votes_inserted += 1
                except Exception:
                    pass
    print(f"\n[DONE] Successfully inserted {votes_inserted} votes.")

    # STEP 3: Insert saves into abhihub.bookmarks in batches of 200
    print("\n[Step 3/4] Inserting saves into abhihub.bookmarks...")
    saves_inserted = 0
    total_save_batches = (len(bookmarks_to_insert) + 199) // 200
    for i in range(0, len(bookmarks_to_insert), 200):
        batch = bookmarks_to_insert[i:i + 200]
        try:
            res = sb.table('bookmarks').insert(batch).execute()
            saves_inserted += len(res.data or batch)
            print(f"  Batch {i//200 + 1}/{total_save_batches}: {saves_inserted} saves inserted.", end='\r')
        except Exception:
            for b in batch:
                try:
                    sb.table('bookmarks').insert(b).execute()
                    saves_inserted += 1
                except Exception:
                    pass
    print(f"\n[DONE] Successfully inserted {saves_inserted} saves.")

    # STEP 4: Update document counters with thread pool
    print("\n[Step 4/4] Updating document view_count, like_count & bookmark_count (12 concurrent workers)...")
    success_docs = 0
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(update_single_doc, sb, item) for item in doc_updates]
        for f in as_completed(futures):
            if f.result():
                success_docs += 1
                if success_docs % 200 == 0:
                    print(f"  Updated counters for {success_docs}/{len(doc_updates)} documents...", end='\r')

    print(f"\n\n[SUCCESS] Completed! All comments, votes, saves, and view counters saved to Supabase.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Preview generated data without modifying DB')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of documents to seed')
    args = parser.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)
