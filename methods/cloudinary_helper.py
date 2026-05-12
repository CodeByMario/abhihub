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
        print(f"Error reading cache: {e}")
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
        
        print(f"Cached {len(files)} files")
    except Exception as e:
        print(f"Error saving cache: {e}")


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
            print(f"Using cached data ({len(cached_files)} files)")
            return cached_files
    
    print("Fetching fresh data from Cloudinary...")
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
        print(f"Error fetching files from Cloudinary: {e}")
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


def search_files(files: List[Dict], query: str) -> List[Dict]:
    """
    Filter files by search query with flexible matching.
    Handles underscores, hyphens, and spaces interchangeably.
    
    Args:
        files: List of file dictionaries
        query: Search query string
    
    Returns:
        Filtered list of files
    """
    if not query:
        return files
    
    def normalize_text(text: str) -> str:
        """Normalize text by replacing special chars with spaces and lowercasing."""
        if not text:
            return ""
        # Replace underscores, hyphens, and other special chars with spaces
        normalized = text.lower()
        for char in ['_', '-', '.', '(', ')', '[', ']', '{', '}']:
            normalized = normalized.replace(char, ' ')
        # Collapse multiple spaces into one
        return ' '.join(normalized.split())
    
    # Normalize the search query
    normalized_query = normalize_text(query)
    query_tokens = normalized_query.split()
    
    filtered = []
    
    for file in files:
        # Normalize all searchable fields
        filename_norm = normalize_text(file.get("filename", ""))
        folder_norm = normalize_text(file.get("folder", ""))
        format_norm = normalize_text(file.get("format", ""))
        path_norm = normalize_text(file.get("path", ""))
        
        # Check if all query tokens are present in any of the fields
        match_found = False
        
        # Try exact phrase match first
        if (normalized_query in filename_norm or
            normalized_query in folder_norm or
            normalized_query in format_norm or
            normalized_query in path_norm):
            match_found = True
        else:
            # Try token-based matching (all tokens must be present)
            combined_text = f"{filename_norm} {folder_norm} {format_norm} {path_norm}"
            if all(token in combined_text for token in query_tokens):
                match_found = True
        
        if match_found:
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
        print(f"Error sorting files: {e}")
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
