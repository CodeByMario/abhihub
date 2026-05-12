# Upload Workflow

## Overview
The upload workflow allows users to upload documents (PDFs, images, etc.) to the platform. It enforces a per‑upload limit on the number of files and validates file size and type.

## Relevant Code
- **app.py** – defines `MAX_FILES_PER_UPLOAD` and the `upload` route handling the POST request.
- **templates/upload.html** – frontend form and JavaScript validation reflecting the limit.
- **static/upload.js** – client‑side validation logic.
- **migrate_data.py** – migration script that creates the `documents` table.

## Scripts
- **Run the server**: `python app.py` starts the Flask app.
- **Database migration**: `python migrate_data.py` ensures the `documents` table exists.

## Usage
When a user selects files and clicks *Upload*, the client checks the count against `MAX_FILES_PER_UPLOAD`. The server validates again before persisting the files and creating a record in Supabase.

## Related Docs
- See `file_access_limits.md` for changing the maximum allowed files.
- See `code_style.md` for style guidelines when updating this feature.
