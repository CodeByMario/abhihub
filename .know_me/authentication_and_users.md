# Authentication & User Management

## Overview
The platform uses Supabase for authentication and user management. This feature covers user registration, login, logout, password resets, and profile management. It includes route protection and role-based access control (e.g., admin).

## Relevant Code
- **`app.py`**:
    - **Decorators**: `auth_required` and `admin_required` (around line 100-150 depending on imports) to protect routes.
    - **Routes**: `/login`, `/signup`, `/logout`, `/reset-password`, `/auth/callback`, `/account`, `/update-account`.
- **`templates/`**:
    - `login.html`, `signup.html`, `reset_password.html` – Authentication UI.
    - `account.html`, `profile.html` – User profile management UI.
- **Supabase Integration**: The app uses `supabase_client.auth` to handle standard identity functions.

## Workflows
1. **Login/Registration**: Users sign up or log in. The backend receives credentials, authenticates with Supabase, and stores the user's session data in Flask's `session` object (e.g., `session['user']`).
2. **Session Management**: `@auth_required` decorator checks for the presence of `session['user']`. If missing, redirects to `/login`.
3. **Profile Management**: Users can update their profile metadata (name, college, branch, year) via `/update-account`. This data is stored in the `profiles` or `students` table in Supabase.
4. **Admin Role**: The `@admin_required` decorator checks if the authenticated user's email matches the configured admin email (often defined in env variables or a specific list).

## Related Docs
- See `about_supabase` for database table definitions related to profiles.
