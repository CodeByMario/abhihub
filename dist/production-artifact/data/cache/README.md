# Store Room Cache Management

This file explains the caching mechanism implemented for the Store Room feature to optimize Cloudinary API usage and reduce costs.

## Caching Strategy

### Cache Location
- **File**: `data/cache/cloudinary_files_cache.json`
- **Format**: JSON with timestamp and files array

### Cache TTL (Time To Live)
- **Duration**: 6 hours
- **Rationale**: Balances freshness with API cost savings

### How It Works

1. **First Request**: 
   - No cache exists
   - Fetches all files from Cloudinary API
   - Saves to cache with timestamp
   - Returns files to user

2. **Subsequent Requests** (within 6 hours):
   - Checks cache file
   - Validates timestamp
   - Returns cached data (no API call)
   - Saves Cloudinary API costs

3. **After 6 Hours**:
   - Cache expires
   - Fresh data fetched from Cloudinary
   - Cache updated with new data

### Cost Savings

**Without Cache:**
- Every page load = 1 API call
- 100 users/day = 100 API calls

**With Cache (6-hour TTL):**
- First load = 1 API call
- Next 99 users = 0 API calls
- 100 users/day = ~4 API calls (one per 6-hour period)

**Savings: ~96% reduction in API calls**

### Manual Cache Refresh

To force a cache refresh, delete the cache file:
```bash
rm data/cache/cloudinary_files_cache.json
```

Or call the API with `use_cache=False`:
```python
files = fetch_all_files(use_cache=False)
```

### Cache Structure

```json
{
  "timestamp": "2026-01-05T01:20:00.000000",
  "count": 150,
  "files": [
    {
      "public_id": "folder/file1",
      "folder": "folder",
      "path": "folder/file1",
      "format": "pdf",
      "bytes": 1024000,
      "size": "1.0 MB",
      "created_at": "2026-01-01T00:00:00Z",
      "url": "https://res.cloudinary.com/...",
      "filename": "file1",
      "resource_type": "image"
    }
  ]
}
```

## Benefits

1. **Cost Reduction**: Minimize Cloudinary API calls
2. **Faster Loading**: Cached data loads instantly
3. **Reduced Latency**: No network requests to Cloudinary
4. **Better UX**: Faster page loads for users
5. **Scalability**: Handle more users without increasing costs

## Monitoring

Check console logs for cache usage:
- "Using cached data (X files)" - Cache hit
- "Fetching fresh data from Cloudinary..." - Cache miss
- "Cached X files" - Data saved to cache
