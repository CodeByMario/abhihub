# File History Management - Complete Setup Guide

## Overview
This guide shows how to integrate the "Previously Accessed Files" section into your dashboard and ensure file access history is properly logged to Supabase.

## Database Setup

### 1. Run the RLS Fix Migration
Execute the SQL in `migrations/fix_file_access_history_rls.sql` on your Supabase database:

```bash
# Using psql
psql -h db.supabase.co -U postgres -d postgres -f migrations/fix_file_access_history_rls.sql

# Or paste the entire SQL file into Supabase SQL editor
```

**What this does:**
- Creates `abhihub.file_access_history` table with proper schema
- Adds `user_id` foreign key reference to `profiles`
- Enables Row Level Security (RLS)
- Creates RLS policies for user access control
- Sets up indexes for query performance
- Creates trigger to auto-sync user_email from profiles

## Backend Changes

### 1. Updated Methods (Already Done)
- **`methods/supabase_helper.py`**:
  - Fixed `save_file_access()` - Now uses user_id and supports document_views logging
  - Fixed `get_user_file_history()` - Now queries by user_id for better performance
  - Added error handling and debugging logs

### 2. New API Endpoint
- **`/api/file-access-history`** (GET)
  - Returns user's file access history
  - Requires authentication
  - Query params: `limit` (default: 20, max: 100)
  - Used by "Previously Accessed Files" UI component

**Example request:**
```bash
curl -X GET 'http://localhost:5000/api/file-access-history?limit=20' \
  -H 'Cookie: session=...'
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "user_email": "user@example.com",
      "file_name": "exam_2024.pdf",
      "file_type": "pdf",
      "file_path": "/path/to/file",
      "file_url": "https://res.cloudinary.com/...",
      "accessed_at": "2026-05-06T14:21:01.708325+00:00"
    }
  ],
  "count": 1
}
```

## Frontend Integration

### Step 1: Add the Script Include
Add this to your dashboard template (e.g., `templates/dashboard.html`):

```html
<!-- Include Font Awesome for icons (if not already included) -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">

<!-- Include the Previously Accessed Files component -->
<script src="{{ url_for('static', filename='js/previously-accessed-files.js') }}"></script>
```

### Step 2: Add the Component Container
Add this HTML snippet where you want the "Previously Accessed Files" section to appear (usually on the dashboard):

```html
<!-- Previously Accessed Files Component -->
<div id="previously-accessed-container" style="display: none;">
  <section class="previously-accessed-section" style="margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px;">
    <h2 style="margin-top: 0; color: #333;">
      <i class="fas fa-history" style="margin-right: 8px;"></i>
      Previously Accessed Files
    </h2>
    
    <div id="file-history-loading" style="text-align: center; padding: 20px; display: none;">
      <i class="fas fa-spinner fa-spin" style="font-size: 24px; color: #007bff;"></i>
      <p>Loading your file history...</p>
    </div>
    
    <div id="file-history-empty" style="text-align: center; padding: 20px; color: #666; display: none;">
      <i class="fas fa-inbox" style="font-size: 32px; margin-bottom: 10px; opacity: 0.5;"></i>
      <p>You haven't accessed any files yet.</p>
    </div>
    
    <div id="file-history-error" style="padding: 15px; background: #f8d7da; color: #721c24; border-radius: 4px; display: none; margin-bottom: 10px;">
      <i class="fas fa-exclamation-circle"></i>
      <span id="file-history-error-message"></span>
    </div>
    
    <div id="file-history-list" style="display: none;">
      <div style="max-height: 400px; overflow-y: auto;">
        <table style="width: 100%; border-collapse: collapse;">
          <thead>
            <tr style="border-bottom: 2px solid #dee2e6;">
              <th style="text-align: left; padding: 10px; color: #666; font-weight: 600;">File Name</th>
              <th style="text-align: left; padding: 10px; color: #666; font-weight: 600;">Type</th>
              <th style="text-align: left; padding: 10px; color: #666; font-weight: 600;">Accessed</th>
              <th style="text-align: center; padding: 10px; color: #666; font-weight: 600;">Action</th>
            </tr>
          </thead>
          <tbody id="file-history-items">
            <!-- Items will be inserted here -->
          </tbody>
        </table>
      </div>
    </div>
  </section>
</div>
```

### Step 3: Initialize the Component
The component automatically initializes on page load. If you need to manually initialize or refresh it:

```javascript
// Create and load the component
const historyComponent = new PreviouslyAccessedFiles();
historyComponent.load(20); // Load last 20 accessed files

// Or refresh later
historyComponent.load(10); // Load last 10 accessed files
```

## How Data Flows

### When User Opens a Document:

1. **Frontend** → User clicks to preview/open a document
2. **Backend** (`/preview` route) → Calls `save_file_access(user_email, file_name, ...)`
3. **save_file_access()** function:
   - Resolves `user_id` from email
   - Increments `view_count` in documents table
   - Inserts record into `file_access_history` table
   - Also logs to `document_views` table (if document_id available)
4. **Database** → Record stored with RLS policies enforced
5. **Later** → User loads dashboard
6. **Frontend JS** → Calls `/api/file-access-history`
7. **Backend** → Returns filtered list (respects RLS)
8. **UI Component** → Displays "Previously Accessed Files" table

## Troubleshooting

### Error: "permission denied for table file_access_history"
**Solution**: Run the RLS fix migration to add proper policies

```sql
-- Check RLS is enabled
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE tablename = 'file_access_history';

-- Check policies exist
SELECT policyname FROM pg_policies 
WHERE tablename = 'file_access_history';
```

### No data showing in "Previously Accessed Files"
1. Check that users are actually accessing files (check logs)
2. Verify data is in the table: 
   ```sql
   SELECT COUNT(*) FROM abhihub.file_access_history;
   ```
3. Check RLS policies allow user to read their own records
4. Verify user_id is being set correctly (not NULL)

### Component not loading
1. Check browser console for JavaScript errors
2. Verify Font Awesome is loaded
3. Ensure `/api/file-access-history` endpoint is accessible
4. Check user is authenticated

### Performance Issues
If querying takes too long:
1. Check indexes are created:
   ```sql
   SELECT * FROM pg_indexes 
   WHERE tablename = 'file_access_history';
   ```
2. Consider archiving old data (older than 90 days)
3. Add pagination to load limit

## Customization

### Change Number of Files Shown
In your template where you call `load()`:

```javascript
historyComponent.load(25); // Show last 25 instead of default 20
```

### Change Table Styling
Modify CSS in `static/js/previously-accessed-files.js`:

```javascript
// Example: Change table row padding
row.style.padding = '15px'; // Instead of '10px'
```

### Add Filters
Extend the component to filter by file type:

```javascript
// Add to PreviouslyAccessedFiles class
filterByType(fileType) {
  const filtered = this.currentFiles.filter(f => f.file_type === fileType);
  this.renderHistory(filtered);
}
```

## Testing

### Manual Testing
1. Log in to your application
2. Access some documents/files
3. Navigate to dashboard
4. Check if "Previously Accessed Files" section appears
5. Verify files are listed with correct timestamps

### Check Database
```sql
-- View all file access records
SELECT id, user_email, file_name, accessed_at 
FROM abhihub.file_access_history 
ORDER BY accessed_at DESC 
LIMIT 10;

-- View by specific user
SELECT * FROM abhihub.file_access_history 
WHERE user_email = 'user@example.com'
ORDER BY accessed_at DESC;

-- Count total records
SELECT COUNT(*) FROM abhihub.file_access_history;
```

### Check Logs
Look for logs in your Flask output:
```
[FILE_ACCESS] Logged access for user@example.com: document.pdf
[FILE_HISTORY] Retrieved 5 file access records for user: user@example.com
```

## Related Endpoints

- **POST `/api/document-view`** - Log document view (uses document_views table)
- **GET `/api/recent-documents`** - Get recently viewed documents
- **GET `/api/file-access-history`** - Get file access history (uses file_access_history table)

## Files Modified/Created

### Database
- `migrations/fix_file_access_history_rls.sql` - RLS policies and schema fixes

### Backend
- `methods/supabase_helper.py` - Updated save_file_access() and get_user_file_history()
- `app.py` - Added /api/file-access-history endpoint

### Frontend
- `static/js/previously-accessed-files.js` - Component code and styling

## Summary

The complete file history system now:
✅ Logs every file access with timestamp, user, and device info
✅ Stores data in two tables (file_access_history and document_views)
✅ Enforces security with RLS policies
✅ Provides API endpoints for retrieving history
✅ Displays "Previously Accessed Files" UI component
✅ Shows proper error messages and loading states
✅ Works with responsive design (mobile-friendly)
