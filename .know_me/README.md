# MemoryWall Feature

## What is it?
MemoryWall lets AbhiHub users create a public page where friends can:
- Describe them in **3 words**
- Leave a **digital signature**
- Write an optional **memory message**
- Pick an **emoji**
- Post **anonymously** or with their name

The creator gets a **Word Cloud** and **Signature Wall** on reveal.

## Routes
| Route | Auth | Purpose |
|---|---|---|
| `/memorywall` | Required | Creator dashboard |
| `/memorywall/create` | Required | Create wall form |
| `/m/<slug>` | Public | Friend submission page |
| `/memorywall/reveal/<wall_id>` | Required (owner only) | Reveal results |
| `POST /api/memorywall/submit` | Public | Submit response |
| `POST /api/memorywall/upload-signature` | Public | Upload signature PNG |
| `GET /api/memorywall/stats/<wall_id>` | Required (owner) | Wall stats JSON |

## Files Added
```
migrations/know_me_tables.sql
methods/know_me.py
methods/know_me_generator.py
templates/know_me/create.html
templates/know_me/dashboard.html
templates/know_me/public_wall.html
templates/know_me/reveal.html
templates/know_me/closed.html
static/css/know-me.css
static/js/know-me.js
```

## Future Roadmap
See `roadmap.md`
