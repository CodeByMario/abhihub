# Credits / Quota System

## Overview
To prevent spam and ensure quality content, the platform implements an upload quota system using "credits". Users consume credits when uploading files, and credits can be replenished over time or through specific administrative actions.

## Relevant Code
- **`app.py`**:
    - `_get_quota()` & `api_get_quota()`: Functions to retrieve the current user's available upload credits.
    - `_consume_credit()`: Deducts a credit from the user's account when an upload is successfully processed.
    - `_grant_upload_credits()`: Administrative or automated function to add credits to a user's account.
    - `upload_gate()`: Route or logic gate that checks if a user has sufficient credits before rendering the upload page or processing an upload request.

## Workflows
1. **Quota Check**: Before a user can access the upload form, `upload_gate()` checks their available credits via `_get_quota()`. If credits are zero or below, the user is blocked from uploading and may see a message explaining the limitation.
2. **Credit Consumption**: Upon a successful file upload (handled in the `upload` route), `_consume_credit()` is called, decrementing the user's available quota in the database (usually stored in the `profiles` or `students` table).
3. **Replenishment**: Credits can be replenished automatically (e.g., via a scheduled background task that resets quotas daily/weekly) or manually granted by administrators via `_grant_upload_credits()`.

## Related Docs
- See `file_access_limits.md` for the per-request file count limits (which operate alongside the overall quota system).
- See `upload_workflow.md` for the complete upload process.
