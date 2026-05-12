# File History Management System - Frontend Integration Guide

## Overview
The file history management system now logs every document view to Supabase and provides APIs to retrieve the user's viewing history.

## API Endpoints

### 1. POST `/api/document-view` - Log a Document View

**Purpose**: Record when a user views a document.

**Authentication**: Required (must be logged in)

**Request Body**:
```json
{
  "document_id": "847afaa6-cec4-48db-9016-2218c169bb87"
}
```

**Response (Success)**:
```json
{
  "success": true,
  "message": "Document view recorded",
  "data": {
    "id": "06fb7bac-7a6c-448c-8b52-58de63232d11",
    "document_id": "847afaa6-cec4-48db-9016-2218c169bb87",
    "user_id": "e2fc0dda-b8e8-41f6-b70e-52f74c3f586c",
    "accessed_at": "2026-05-06T14:21:01.708325+00:00"
  }
}
```

**Response (Error)**:
```json
{
  "success": false,
  "message": "Missing document_id"
}
```

**Example JavaScript**:
```javascript
async function logDocumentView(documentId) {
  try {
    const response = await fetch('/api/document-view', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        document_id: documentId
      })
    });
    
    const data = await response.json();
    if (data.success) {
      console.log('Document view logged:', data.data);
    } else {
      console.error('Failed to log view:', data.message);
    }
  } catch (error) {
    console.error('Error logging document view:', error);
  }
}
```

### 2. GET `/api/recent-documents` - Get Recently Viewed Documents

**Purpose**: Retrieve the list of documents the user has recently viewed.

**Authentication**: Required (must be logged in)

**Query Parameters**:
- `limit` (optional, default: 20, max: 100) - Number of documents to return

**Response (Success)**:
```json
{
  "success": true,
  "data": [
    {
      "view_id": "06fb7bac-7a6c-448c-8b52-58de63232d11",
      "accessed_at": "2026-05-06T14:21:01.708325+00:00",
      "document": {
        "id": "847afaa6-cec4-48db-9016-2218c169bb87",
        "title": "CAE1 Submission",
        "subject_id": "abc123",
        "uploader_id": "xyz789",
        "file_url": "https://res.cloudinary.com/...",
        "document_category": "assisment"
      }
    },
    {
      "view_id": "7c5c8bb2-9d7d-469e-9c13-7f8e9a0b1c2d",
      "accessed_at": "2026-05-05T23:28:20.498901+00:00",
      "document": {
        "id": "9d4a7e3f-5b2c-4d8a-9f1e-6c3d5b7a9e2f",
        "title": "Daa - CAE2",
        "subject_id": "def456",
        "uploader_id": "abc123",
        "file_url": "https://res.cloudinary.com/...",
        "document_category": "notes"
      }
    }
  ],
  "count": 2
}
```

**Response (Error)**:
```json
{
  "success": false,
  "message": "User not authenticated",
  "data": [],
  "count": 0
}
```

**Example JavaScript**:
```javascript
async function getRecentDocuments(limit = 20) {
  try {
    const response = await fetch(`/api/recent-documents?limit=${limit}`);
    const data = await response.json();
    
    if (data.success) {
      console.log(`Retrieved ${data.count} recent documents:`, data.data);
      return data.data;
    } else {
      console.error('Failed to get recent documents:', data.message);
      return [];
    }
  } catch (error) {
    console.error('Error fetching recent documents:', error);
    return [];
  }
}
```

## Integration Points

### When to Call `logDocumentView()`
Call this endpoint when:
- User opens/previews a document
- User downloads a document
- User views the document details page
- Any significant interaction with a document

**Example in document viewer**:
```javascript
function openDocumentPreview(documentId, fileUrl) {
  // Log the view
  logDocumentView(documentId);
  
  // Then open the preview
  window.open(fileUrl, '_blank');
}
```

### Where to Display Recent Documents
Consider displaying recent documents in:
- User dashboard/homepage (Recently Accessed section)
- Sidebar widget showing quick links to recent files
- Search results with a "Recently viewed" filter
- Settings page showing user's history

**Example UI component**:
```javascript
async function displayRecentDocumentsWidget() {
  const docs = await getRecentDocuments(5);
  
  const html = docs.map(item => `
    <div class="recent-doc-item">
      <h4>${item.document.title}</h4>
      <p>Accessed: ${new Date(item.accessed_at).toLocaleDateString()}</p>
      <a href="/preview?file_path=${item.document.file_url}">
        View Document
      </a>
    </div>
  `).join('');
  
  document.getElementById('recent-docs-widget').innerHTML = html;
}
```

## Database Details

### Supabase Table Schema
```sql
CREATE TABLE abhihub.document_views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES abhihub.documents(id) ON DELETE CASCADE,
    user_id UUID REFERENCES abhihub.profiles(id) ON DELETE SET NULL,
    ip_address TEXT,
    device_type TEXT,
    accessed_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Data Captured
- `id`: Unique identifier for each view
- `document_id`: The document being viewed
- `user_id`: The user viewing the document
- `ip_address`: User's IP address (automatically captured)
- `device_type`: Device type (desktop, mobile, tablet - automatically detected)
- `accessed_at`: Timestamp of the view

## Testing

### Test Files
Two test files are provided:

1. **test_document_history.py** - Unit tests
```bash
python test_document_history.py
```

2. **test_document_history_integration.py** - Integration tests with real data
```bash
python test_document_history_integration.py
```

### Manual Testing
```bash
# 1. Make sure you're logged in

# 2. Log a document view
curl -X POST http://localhost:5000/api/document-view \
  -H "Content-Type: application/json" \
  -d '{"document_id": "847afaa6-cec4-48db-9016-2218c169bb87"}'

# 3. Get recent documents
curl http://localhost:5000/api/recent-documents?limit=10
```

## Error Handling

All endpoints return proper HTTP status codes:
- `200` - Success
- `400` - Bad request (missing or invalid parameters)
- `401` - Unauthorized (not logged in)
- `500` - Server error

Always check the `success` field in the response:
```javascript
if (response.success) {
  // Handle success
} else {
  // Handle error - check response.message
}
```

## Performance Considerations

1. **Logging is asynchronous** - Views are logged in the background and don't block user interactions
2. **Query limit capped at 100** - Prevents accidentally querying too much data
3. **Duplicate filtering** - Recent documents list automatically removes duplicate entries
4. **Indexed queries** - Supabase indexes ensure fast retrieval

## Privacy & Security

1. Users can only see their own history
2. Admins can see all history (admin-only policies in Supabase)
3. IP addresses and device info are captured for analytics
4. Views are soft-linked (orphaned views are removed if document is deleted)

## Future Enhancements

Possible improvements:
- Analytics dashboard showing most viewed documents
- Document download history tracking
- Time-based statistics (peak viewing times)
- Collaborative viewing indicators
- Search history tracking
