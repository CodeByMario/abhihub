# File Access Limits

## Overview
The application restricts the number of files a user can upload in a single request to prevent abuse and manage storage costs. The default limit is **3 files per upload**.

## Relevant Code
- **`app.py`** – constant `MAX_FILES_PER_UPLOAD` near the top of the file controls the limit and the validation logic in the `/upload` route.
- **`templates/upload.html`** – frontend validation that disables the file input when the selected files exceed the limit.
- **`static/js/upload.js`** – optional client‑side script that displays an error message if the user selects too many files.

## Scripts
- **Adjust Limit**: Edit `app.py` and change `MAX_FILES_PER_UPLOAD` to the desired integer.
- **Run Migrations**: No DB migration required for this feature.

## Usage
When a user attempts to upload files:
1. The frontend checks the number of selected files against `MAX_FILES_PER_UPLOAD` and shows an inline warning if exceeded.
2. The backend re‑validates the count; if it exceeds the limit it returns a `400 Bad Request` with message `"Upload limit exceeded"`.

## Related Docs
- See `file_access_history.md` for logging of uploaded files.
- See `code_style.md` for style guidelines when updating this logic.

The above content shows the entire, complete file contents of the requested file.
