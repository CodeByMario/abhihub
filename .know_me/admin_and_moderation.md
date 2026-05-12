# Admin & Moderation (Store Room)

## Overview
The platform includes an admin control panel and moderation tools designed to review, verify, and manage user-uploaded content. A dedicated "Store Room" interface allows administrators to process unverified documents before they are publicly visible.

## Relevant Code
- **`app.py`**:
    - `admin_required`: Decorator used to protect administrative routes.
    - `admin_control_panel()` (`/admin`): The main dashboard for administrators.
    - `verify_file()` & `store_room_api_verify()`: Endpoints for marking an uploaded document as verified/approved.
    - `report_suspect()`: Endpoint for users or automated systems to flag inappropriate content.
    - `store_room_*` functions (e.g., `store_room()`, `store_room_api_files()`, `store_room_api_label()`, `store_room_api_rename_file()`): Routes managing the 'Store Room', a staging area for newly uploaded documents waiting for manual review or automated categorization.
- **`app_store_room_endpoint.py`**: A dedicated module that likely offloads or structures some of the specific Store Room API endpoints.
- **`templates/admin.html` & `templates/store_room.html`**: The UI interfaces for administration and content moderation.

## Workflows
1. **Upload & Verification**: When users upload files, they are initially flagged as `verified = False` in the database.
2. **Store Room Queue**: Admins access the Store Room to see a queue of unverified documents (`store_room_api_verification_queue`).
3. **Moderation Actions**: From the interface, admins can review the document, assign proper labels (`store_room_api_label`), rename it if necessary (`store_room_api_rename_file`), and finally approve it (`store_room_api_verify`).
4. **Visibility**: Once verified, the document becomes visible in standard searches and public directories.
5. **Reporting**: The `report_suspect` route handles user reports, flagging documents for admin review.
