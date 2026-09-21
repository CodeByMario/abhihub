"""
Backfill Script: PDF Text Preview Extraction for Existing Documents.

Extracts text from the first 2-3 pages of existing PDF documents,
formats a ~150-word excerpt, and updates the database record.
Includes dry-run support, batching, and error handling.

Usage:
  python scripts/backfill_pdf_preview.py --dry-run
  python scripts/backfill_pdf_preview.py --batch-size 20
"""

import os
import sys
import io
import time
import logging
import argparse
import requests

# Add repository root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from methods.supabase_helper import init_supabase

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')


def extract_pdf_preview_from_url(url: str, max_words: int = 150) -> str:
    """Download PDF stream and extract up to max_words from the first 2-3 pages."""
    try:
        import pypdf
    except ImportError:
        logging.error("pypdf is not installed. Please run: pip install pypdf")
        return ""

    try:
        resp = requests.get(url, timeout=15, stream=True)
        if resp.status_code != 200:
            logging.warning(f"Failed to fetch {url}: HTTP {resp.status_code}")
            return ""

        pdf_bytes = io.BytesIO(resp.content)
        reader = pypdf.PdfReader(pdf_bytes)
        num_pages = len(reader.pages)
        pages_to_read = min(num_pages, 3)

        chunks = []
        for p in range(pages_to_read):
            text = reader.pages[p].extract_text()
            if text:
                chunks.append(text)

        full_text = ' '.join(chunks).strip()
        words = full_text.split()
        if not words:
            return ""

        return ' '.join(words[:max_words])
    except Exception as e:
        logging.warning(f"Error extracting PDF preview: {e}")
        return ""


def run_backfill(batch_size: int = 20, dry_run: bool = True):
    client = init_supabase()
    if not client:
        logging.error("Could not initialize Supabase client.")
        return

    logging.info(f"Starting PDF backfill (dry_run={dry_run}, batch_size={batch_size})...")

    # Fetch PDF documents
    try:
        res = client.table('documents') \
            .select('id, title, file_url, file_type, description') \
            .eq('file_type', 'pdf') \
            .limit(batch_size) \
            .execute()
        
        docs = res.data or []
        logging.info(f"Fetched {len(docs)} PDF documents to process.")

        updated_count = 0
        for doc in docs:
            doc_id = doc.get('id')
            title = doc.get('title')
            url = doc.get('file_url')
            if not url:
                continue

            logging.info(f"Processing doc {doc_id}: {title}")
            preview = extract_pdf_preview_from_url(url)

            if not preview:
                logging.info(f"  -> No text extracted (likely scanned or empty image PDF).")
                continue

            logging.info(f"  -> Extracted {len(preview.split())} words preview.")

            if not dry_run:
                # Update document record
                try:
                    update_res = client.table('documents').update({
                        'extracted_text_preview': preview
                    }).eq('id', doc_id).execute()
                    if update_res.data:
                        updated_count += 1
                        logging.info(f"  -> Updated doc {doc_id} successfully.")
                except Exception as update_err:
                    logging.error(f"  -> Database update failed: {update_err}")
            else:
                updated_count += 1

            time.sleep(0.5)

        logging.info(f"Backfill finished. Processed {len(docs)} documents, updated {updated_count} (dry_run={dry_run}).")
    except Exception as e:
        logging.error(f"Backfill failed with error: {e}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Backfill PDF text previews for documents.")
    parser.add_argument('--dry-run', action='store_true', default=False, help="Run without persisting changes to DB.")
    parser.add_argument('--batch-size', type=int, default=20, help="Number of documents to process in one run.")
    args = parser.parse_args()

    run_backfill(batch_size=args.batch_size, dry_run=args.dry_run)
