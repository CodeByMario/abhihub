"""
Cloudinary Helper Module
Provides functions to interact with Cloudinary API for fetching and managing files.
"""

import os
import cloudinary
import cloudinary.api
from dotenv import load_dotenv
from typing import List, Dict, Optional
import json
from datetime import datetime, timedelta
import logging

# Load environment variables
load_dotenv()

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# Cache configuration
CACHE_DIR = "data/cache"
CACHE_FILE = os.path.join(CACHE_DIR, "cloudinary_files_cache.json")
CACHE_TTL_HOURS = 6  # Cache expires after 6 hours


def _get_cached_files() -> Optional[List[Dict]]:
    """
    Get files from cache if available and not expired.
    
    Returns:
        Cached files list or None if cache is invalid/expired
    """
    if not os.path.exists(CACHE_FILE):
        return None
    
    try:
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)
        
        # Check if cache is expired
        cache_time = datetime.fromisoformat(cache_data.get('timestamp', ''))
        if datetime.now() - cache_time > timedelta(hours=CACHE_TTL_HOURS):
            return None
        
        return cache_data.get('files', [])
    except Exception as e:
        logging.error(f"Error reading cache: {e}")
        return None


def _save_to_cache(files: List[Dict]) -> None:
    """
    Save files to cache with timestamp.
    
    Args:
        files: List of file dictionaries to cache
    """
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'files': files,
            'count': len(files)
        }
        
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f)
        
        logging.info(f"Cached {len(files)} files")
    except Exception as e:
        logging.error(f"Error saving cache: {e}")


def fetch_all_files(resource_type: str = "image", use_cache: bool = True) -> List[Dict]:
    """
    Fetch all files from Cloudinary with metadata.
    Uses caching to minimize API calls and reduce costs.
    
    Args:
        resource_type: Type of resource to fetch (image, video, raw, auto)
        use_cache: Whether to use cached data if available
    
    Returns:
        List of dictionaries containing file metadata
    """
    # Try to get from cache first
    if use_cache:
        cached_files = _get_cached_files()
        if cached_files is not None:
            logging.info(f"Using cached data ({len(cached_files)} files)")
            return cached_files
    
    logging.info("Fetching fresh data from Cloudinary...")
    results = []
    next_cursor = None

    try:
        while True:
            response = cloudinary.api.resources(
                resource_type=resource_type,
                max_results=500,
                next_cursor=next_cursor,
                fields=[
                    "public_id",
                    "folder",
                    "format",
                    "bytes",
                    "created_at",
                    "secure_url",
                    "resource_type"
                ]
            )

            for r in response.get("resources", []):
                folder = r.get("folder", "")
                public_id = r["public_id"]
                
                results.append({
                    "public_id": public_id,
                    "folder": folder,
                    "path": f"{folder}/{public_id}".strip("/"),
                    "format": r.get("format", "unknown"),
                    "bytes": r.get("bytes", 0),
                    "size": format_file_size(r.get("bytes", 0)),
                    "created_at": r.get("created_at"),
                    "url": r.get("secure_url", ""),
                    "filename": public_id.split("/")[-1],
                    "resource_type": r.get("resource_type", "image")
                })

            next_cursor = response.get("next_cursor")
            if not next_cursor:
                break

    except Exception as e:
        logging.error(f"Error fetching files from Cloudinary: {e}")
        return []

    # Save to cache for future use
    if results:
        _save_to_cache(results)

    return results


def format_file_size(bytes_size: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        bytes_size: Size in bytes
    
    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"



def _normalize_text(text: str) -> str:
    """Shared normalizer: lowercase, replace separators with space, collapse."""
    if not text:
        return ''
    for ch in ['_', '-', '.', '(', ')', '[', ']', '{', '}']:
        text = text.replace(ch, ' ')
    return ' '.join(text.lower().split())


def build_inverted_index(files: List[Dict]) -> Dict[str, List[int]]:
    """
    Build a token → [file_index, ...] map for O(1) multi-token lookup.
    Call once when cache is populated, not on every search request.
    """
    index: Dict[str, List[int]] = {}
    for i, file in enumerate(files):
        raw = ' '.join(filter(None, [
            file.get('filename', ''),
            file.get('folder', ''),
            file.get('format', ''),
            file.get('storage_id', ''),
            file.get('path', ''),
        ]))
        tokens = set(_normalize_text(raw).split())
        for tok in tokens:
            if tok:
                index.setdefault(tok, []).append(i)
    return index


def search_files(files: List[Dict], query: str, _index: Optional[Dict] = None) -> List[Dict]:
    """
    Filter files by search query.
    Uses inverted index (O(intersect)) when available, falls back to linear scan.

    Args:
        files:  List of file dicts (the full unlabeled list)
        query:  Search query string
        _index: Optional pre-built inverted index from build_inverted_index()

    Returns:
        Filtered list of files
    """
    if not query:
        return files

    normalized = _normalize_text(query)
    tokens = [t for t in normalized.split() if t]
    if not tokens:
        return files

    if _index is not None:
        # Intersect posting lists — all tokens must match
        candidate_sets = [set(_index.get(t, [])) for t in tokens]
        if not candidate_sets:
            return []
        matched_indices = candidate_sets[0]
        for s in candidate_sets[1:]:
            matched_indices &= s
        return [files[i] for i in sorted(matched_indices) if i < len(files)]

    # Fallback: original linear scan (safe if index not available)
    filtered = []
    for file in files:
        combined = _normalize_text(' '.join(filter(None, [
            file.get('filename', ''), file.get('folder', ''),
            file.get('format', ''), file.get('path', ''),
            file.get('storage_id', ''), file.get('provider_public_id', ''),
        ])))
        if all(t in combined for t in tokens):
            filtered.append(file)
    return filtered




def sort_files(files: List[Dict], sort_by: str = "created_at", order: str = "desc") -> List[Dict]:
    """
    Sort files by specified field.
    
    Args:
        files: List of file dictionaries
        sort_by: Field to sort by (created_at, filename, bytes, format)
        order: Sort order (asc or desc)
    
    Returns:
        Sorted list of files
    """
    reverse = (order == "desc")
    
    # Map sort_by to actual field names
    sort_field_map = {
        "date": "created_at",
        "name": "filename",
        "size": "bytes",
        "format": "format"
    }
    
    sort_field = sort_field_map.get(sort_by, sort_by)
    
    try:
        sorted_files = sorted(
            files,
            key=lambda x: x.get(sort_field, ""),
            reverse=reverse
        )
        return sorted_files
    except Exception as e:
        logging.error(f"Error sorting files: {e}")
        return files


def filter_files(files: List[Dict], format_filter: Optional[str] = None, 
                 folder_filter: Optional[str] = None) -> List[Dict]:
    """
    Apply format and folder filters to files.
    
    Args:
        files: List of file dictionaries
        format_filter: Format to filter by (e.g., "pdf", "jpg")
        folder_filter: Folder to filter by
    
    Returns:
        Filtered list of files
    """
    filtered = files
    
    if format_filter:
        format_filter = format_filter.lower()
        filtered = [f for f in filtered if f.get("format", "").lower() == format_filter]
    
    if folder_filter:
        folder_filter = folder_filter.lower()
        filtered = [f for f in filtered if folder_filter in f.get("folder", "").lower()]
    
    return filtered


def get_unique_formats(files: List[Dict]) -> List[str]:
    """
    Get list of unique file formats from files.
    
    Args:
        files: List of file dictionaries
    
    Returns:
        Sorted list of unique formats
    """
    formats = set()
    for file in files:
        format_val = file.get("format", "").lower()
        if format_val:
            formats.add(format_val)
    
    return sorted(list(formats))


def get_unique_folders(files: List[Dict]) -> List[str]:
    """
    Get list of unique folders from files.
    
    Args:
        files: List of file dictionaries
    
    Returns:
        Sorted list of unique folders
    """
    folders = set()
    for file in files:
        folder_val = file.get("folder", "")
        if folder_val:
            folders.add(folder_val)
    
    return sorted(list(folders))
