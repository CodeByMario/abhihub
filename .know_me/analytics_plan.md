# MemoryWall Analytics Plan

## GA4 Property: G-EH5BGS9BEG (existing)

## Events Tracked

All events use `window.safeGtag()` (deduplication wrapper from `google_tag.html`).

| Event Name | Trigger | Key Params |
|---|---|---|
| `memorywall_view` | Page load on `/memorywall` or `/m/<slug>` | `view: 'dashboard' \| 'public_wall'`, `slug` |
| `memorywall_create` | Page load on `/memorywall/create` | — |
| `memorywall_submit` | Successful form submission | `wall_id` |
| `memorywall_share` | Share button clicked | `method: 'copy_link' \| 'whatsapp'` |
| `memorywall_reveal` | Page load on `/memorywall/reveal/<id>` | — |

## Implementation
Events are fired inside `static/js/know-me.js` on:
- `DOMContentLoaded` (page views)
- Form submit success callback
- Share button click handlers

## Analytics extend `window.AbhiHubTracking` via `Object.assign` in `know-me.js`.
No modifications to `google_tag.html`.

## Success Metrics to Monitor in GA4
- `walls_created` → count of `memorywall_create` events
- `responses_submitted` → count of `memorywall_submit` events
- `reveal_rate` → `memorywall_reveal` / `memorywall_create`
- `share_rate` → `memorywall_share` / `memorywall_create`
- Average session time on `/m/<slug>` pages
