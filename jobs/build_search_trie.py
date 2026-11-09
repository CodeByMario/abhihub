"""
Offline Trie & Inverted Index Build Job.
Periodically aggregates search query frequencies & taxonomy into an in-memory Trie.
"""
import os
import json
import logging
import threading
from typing import Optional
from services.search_trie import AutocompleteTrie, InvertedIndex

logger = logging.getLogger(__name__)

_GLOBAL_TRIE: Optional[AutocompleteTrie] = None
_GLOBAL_INDEX: Optional[InvertedIndex] = None
_TRIE_LOCK = threading.Lock()
_QUERY_FREQUENCIES: dict = {}
_LOG_LOCK = threading.Lock()

def record_search_query(query: str) -> None:
    """Record query frequency from search requests (fire-and-forget)."""
    clean = query.strip().lower()
    if len(clean) < 2:
        return
    with _LOG_LOCK:
        _QUERY_FREQUENCIES[clean] = _QUERY_FREQUENCIES.get(clean, 0) + 1

def build_search_indexes() -> AutocompleteTrie:
    """Build Trie & Inverted Index from taxonomy and aggregated query counts."""
    global _GLOBAL_TRIE, _GLOBAL_INDEX
    trie = AutocompleteTrie(k=5)
    index = InvertedIndex()

    # 1. Populate from recorded query logs (highest priority by frequency)
    with _LOG_LOCK:
        for q, count in _QUERY_FREQUENCIES.items():
            trie.insert(q, score=count * 10)

    # 2. Populate from taxonomy
    try:
        from methods.search_api import get_taxonomy
        taxonomy = get_taxonomy()

        # Subjects
        for s in taxonomy.get('subjects', []):
            name = s.get('name', '')
            code = s.get('subject_code', '')
            if name:
                trie.insert(name, score=50)
                index.add(s.get('id', name), name)
            if code:
                trie.insert(code, score=60)
                index.add(s.get('id', code), code)

        # Subject Aliases
        for a in taxonomy.get('subject_aliases', []):
            alias = a.get('alias', '')
            if alias:
                trie.insert(alias, score=40)

        # Colleges
        for c in taxonomy.get('colleges', []):
            c_name = c.get('name', '')
            c_abbr = c.get('abbreviation', '')
            if c_name:
                trie.insert(c_name, score=30)
                index.add(c.get('id', c_name), c_name)
            if c_abbr:
                trie.insert(c_abbr, score=40)
                index.add(c.get('id', c_abbr), c_abbr)
    except Exception as e:
        logger.warning("Failed to populate taxonomy into Trie: %s", e)

    with _TRIE_LOCK:
        _GLOBAL_TRIE = trie
        _GLOBAL_INDEX = index

    logger.info("Search Trie & Inverted Index built successfully.")
    return trie

def get_cached_trie() -> AutocompleteTrie:
    """Return in-memory Trie, building lazily on first access."""
    global _GLOBAL_TRIE
    if _GLOBAL_TRIE is None:
        with _TRIE_LOCK:
            if _GLOBAL_TRIE is None:
                return build_search_indexes()
    return _GLOBAL_TRIE
