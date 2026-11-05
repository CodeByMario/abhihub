"""
jobs/sync_openrouter.py — CLI and Cron runner for syncing OpenRouter free catalog.
"""
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def main():
    from services.catalog_sync import sync_all
    count = await sync_all()
    print(f"✅ Sync completed: {count} verified models in catalog.")

if __name__ == "__main__":
    asyncio.run(main())
