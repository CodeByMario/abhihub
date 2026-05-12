# Realtime Ranking System

## Overview
The Realtime Ranking System updates user leaderboards instantly as users interact with the platform (uploads, likes, views). It leverages Supabase realtime subscriptions to push ranking changes to connected clients.

## Relevant Code
- `app.py` – endpoint `/api/update-rank` that recomputes a user's rank.
- `scheduled_tasks.py` – background job `recalculate_all_ranks` used for periodic full recomputation.
- `push_notifications.py` – optional push to notify users when their rank improves.
- `templates/leaderboard.html` – client‑side JavaScript that opens a Supabase realtime channel and updates the DOM.

## Scripts
- **Full Recalculation**: `python scheduled_tasks.py --recalc-ranks` recomputes ranks for all users.
- **Trigger Update**: The frontend calls `fetch('/api/update-rank', { method: 'POST' })` after actions that affect rank.

## Usage
When a user uploads a document or receives a like, the frontend sends a POST to `/api/update-rank` with the user's UUID. The backend:
1. Retrieves the user's contribution statistics.
2. Calculates the new rank.
3. Writes the rank to the `profiles` table.
4. Publishes a Supabase realtime event on the `rank_updates` channel.
5. The client subscribed to that channel receives the new rank and updates the leaderboard UI instantly.

**Client Example** (in `leaderboard.html`):
```js
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
supabase.channel('public:rank_updates')
  .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'profiles' }, payload => {
    const { id, rank } = payload.new
    document.querySelector(`#rank-${id}`).textContent = rank
  })
  .subscribe()
```
