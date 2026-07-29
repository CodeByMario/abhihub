# MemoryWall Feature Spec

## Product Goal
Allow any AbhiHub user to create a public "MemoryWall" page. Friends visit the page, submit 3 words describing the creator, draw a signature, and optionally leave a memory. The creator reveals a word cloud and signature composite.

## User Stories

### Creator
- As a creator, I can create one MemoryWall with my name, college, branch, and grad year.
- As a creator, I get a unique public link (`/m/<slug>`) to share with friends.
- As a creator, I can share via WhatsApp or copy link from my dashboard.
- As a creator, I can reveal my wall at any time to see a word cloud and signature wall.
- As a creator, I can see how many responses my wall has.

### Friend (Submitter)
- As a friend, I can visit the public link without logging in.
- As a friend, I enter 3 words that describe the person.
- As a friend, I can draw my digital signature.
- As a friend, I can leave an optional memory message and pick an emoji.
- As a friend, I can choose to post anonymously.
- As a friend, I see a success confirmation after submitting.

## Business Rules
1. One wall per user (enforced server-side)
2. Walls are permanent once created (status: active | closed)
3. Max 5 submissions per IP per hour (rate limiting via IP hash)
4. Honeypot field rejects bots
5. Raw IPs are never stored — SHA256 hash only
6. Signatures: PNG only, max 512KB, PIL-verified
7. Wall slugs are unique; retry on collision

## Non-Goals (Phase 1)
- No AI personality summary
- No PDF export
- No poster/T-shirt generation
- No QR codes
- No multiple walls per user

## Acceptance Criteria
- [ ] `/memorywall` requires login, shows dashboard
- [ ] `/memorywall/create` creates wall and redirects to dashboard
- [ ] `/m/<slug>` is publicly accessible (no login required)
- [ ] Form submission triggers `memorywall_submit` GA4 event
- [ ] Submitting with honeypot field filled returns 400
- [ ] 6th submission from same IP in 1 hour returns 429
- [ ] Reveal page shows word cloud image (if wordcloud installed)
- [ ] Reveal page shows signature wall image
- [ ] Share buttons open correct WhatsApp URL / copy correct link
