# Document Interactions

## Overview
Users can interact with documents on the platform by liking, bookmarking, and commenting. These interactions drive engagement and influence document ranking and user reputation.

## Relevant Code
- **`app.py`**:
    - `toggle_like_route()` (`/api/toggle-like`): Handles adding or removing a like on a document for the current user.
    - `toggle_bookmark_route()` (`/api/toggle-bookmark`): Handles saving or removing a document from the user's bookmarks/saved items.
    - `add_comment_route()` (`/api/comments/add`): Allows users to post a comment on a specific document.
    - `get_comments_route()` (`/api/comments/<doc_id>`): Retrieves the comment thread for a given document.
- **`templates/view.html` & `templates/pdf_viewer.html`**: UI templates displaying the interaction buttons (Like, Bookmark) and the comment section.

## Interaction Mechanics
1. **Likes**: When a user clicks the Like button, an async request is sent to the backend. The backend updates the `likes` counter on the document and records the interaction in a user-document relationship table (e.g., `user_likes` or similar in Supabase) to prevent multiple likes from the same user. This event often triggers a rank recalculation.
2. **Bookmarks**: Functionally similar to likes, but stored in a separate relationship (e.g., `user_bookmarks`). Bookmarked documents appear in a dedicated section on the user's dashboard or profile.
3. **Comments**: Comments are stored in a `comments` table with a foreign key to the `documents` table and the `profiles` (user) table. They are fetched asynchronously when the document view page loads.

## Related Docs
- See `realtime_ranking.md` for how interactions like "Likes" influence the realtime leaderboard.
