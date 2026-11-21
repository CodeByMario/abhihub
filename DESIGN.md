# AbhiHub Architecture & Design Specification
## Load-Aware Queue, Tiering, and Controlled Advertising System

### 1. Architectural Principles
- **Platform**: Vercel Serverless (Fluid Compute). Strict zero-process-state model (no background workers, daemon threads, APScheduler, or shared process memory).
- **CPU Quota Budgeting**: Fluid Active CPU monthly allocation (4h/month = ~480 s/day; operational safety target = 335 s/day with buffer).
- **State Store**: Upstash Redis REST API (`upstash-redis`). Minimal round-trips per request.
- **Commercial Separation**: All monetization features (`FEATURE_PAYMENTS`, `FEATURE_ADS`) are disabled by default (`false`) to comply with Vercel Hobby non-commercial constraints.
- **Critical Path Exemption**: Public resources, PDF viewing, auth, login, and search are never queued. Search degrades gracefully from RapidFuzz to prefix/exact matching under load.

---

### 2. Configuration Keys (Environment Variables)

| Config Key | Default | Description |
| :--- | :--- | :--- |
| `FEATURE_PAYMENTS` | `false` | Enables Razorpay checkout and premium subscriptions (Requires Vercel Pro). |
| `FEATURE_ADS` | `false` | Enables waiting-screen Adsterra iframe banners (Requires Vercel Pro). |
| `DAILY_CPU_BUDGET_S` | `335` | Daily CPU safety threshold in seconds (~70% of 480 s/day allowance). |
| `DAILY_AI_FREE_POOL` | `900` | Account-wide limit of OpenRouter free tier requests per day (100 reserved). |
| `QUEUE_RATE_LIMIT_PER_MIN` | `15` | Global concurrency cap to stay below OpenRouter's 20 req/min limit. |
| `UPSTASH_REDIS_REST_URL` | `""` | Upstash Redis REST endpoint. |
| `UPSTASH_REDIS_REST_TOKEN` | `""` | Upstash Redis REST authentication token. |

---

### 3. Redis Key Schema

| Key Pattern | Type | TTL | Purpose |
| :--- | :--- | :--- | :--- |
| `budget:cpu:YYYY-MM-DD` | `integer` | 48h | Cumulative daily thread CPU time consumed in milliseconds (`INCRBY`). |
| `budget:state` | `string` | 60s | Current load state: `green` (<60%), `yellow` (60-85%), `red` (>85%). |
| `rate:openrouter:minute` | `integer` | 60s | Token bucket counter for OpenRouter requests (capped at 15/min). |
| `rate:openrouter:daily:YYYY-MM-DD` | `integer` | 48h | Global free-pool daily consumption (capped at 900/day). |
| `queue:ai` | `zset` | N/A | Queue members ordered by admission timestamp score. |
| `heartbeat:ai` | `zset` | N/A | Last-seen heartbeats for active queue tabs (evicted after 30s). |
| `ticket:ai:<ticket_id>` | `string` | 90s | Single-use admission ticket consumed atomically via `GETDEL`. |
| `cache:ocr:<doc_id>` | `string` | 30d | Extracted OCR text for PDF documents, invalidated on document update. |
| `cache:search:<query_hash>` | `string` | 1h-6h | Cached search response payloads for normalized queries. |
| `cache:know_me:<wall_id>` | `string` | 30d | Stored CDN render URL for Know-Me signature walls/wordclouds. |
| `cache:ai:<doc_id>:<query_hash>` | `string` | 2h | Cached AI assistant answers for identical document questions. |
| `cfg:ads` | `hash` | N/A | Admin ad-intensity settings (`level`, `auto_guard`, `guard_abandon_pct`). |
| `ads:throttled` | `string` | 6h | Automatic degradation flag triggered when wait abandonment exceeds threshold. |

---

### 4. Endpoints & Interfaces

#### Public & Queue Operations
- `POST /api/queue/join`: Enqueues request; returns `{status: "ready", ticket: "..."}`, `{status: "waiting", qid: "...", eta_s: 12}`, or `{status: "exhausted"}`.
- `GET /api/queue/status/<qid>`: Returns real-time position, estimated wait, adaptive polling interval (`2s-10s`), and allowed ad slots.
- `POST /api/queue/heartbeat`: Tab keepalive signal to prevent ghost queuing.
- `POST /api/ai/chat` (alias `/api/ai/assistant`): Validates single-use ticket for free tier users; streams or returns assistant responses.
- `POST /api/extract-ocr`: Returns extracted native or OCR text (reads from cache when available).
- `GET /api/v2/search`: Returns filtered documents. Under `red` budget load, disables fuzzy search and uses prefix/exact matching.

#### Advertising & Administrative
- `GET /public/ad-frame.html`: Sandboxed static iframe runner for Adsterra responsive slots.
- `GET /admin/api/ads`: Returns current configuration, telemetry counts, and throttle status.
- `POST /admin/api/ads`: Updates and clamps ad-intensity levels.

---

### 5. Tier Limits & Admission Matrix

| Feature | Free Tier | Premium Tier |
| :--- | :--- | :--- |
| **AI Assistant** | 3 queries/day, queued via OpenRouter `:free` pool | 30 queries/day (fair-use ~400/mo), no queue, direct paid model |
| **OCR Document Extraction** | 3 extractions/day | 40 extractions/day |
| **Search** | Exact/Prefix under heavy load; Fuzzy under normal load | Full Fuzzy Search |
| **Know-Me Regeneration** | 1 initial render cached; limited re-renders | Unlimited re-renders |
| **Waiting Screen Ads** | Displayed strictly when waiting in queue | Never displayed |

---

### 6. Premium Plans (Razorpay)

| Plan | Price | Duration | Entitlements |
| :--- | :--- | :--- | :--- |
| **Day Pass** | ₹29 | 24 Hours | Instant AI, No Queue, No Ads, Fast OCR (40/day), 15m Signed PDF URLs |
| **Exam Sprint** | ₹79 | 7 Days | Full exam cram access, Paid LLM fallback, Unmetered viewing |
| **Semester Pro** | ₹199 | 6 Months | Complete semester pass, 30 AI queries/day (400/month fair-use) |

---

### 7. Production Upgrade Checklist (Prior to Commercial Launch)
1. **Hosting**: Upgrade Vercel Hobby plan to Vercel Pro before setting `FEATURE_PAYMENTS=true` or `FEATURE_ADS=true`.
2. **Adsterra Compliance**: Configure network filter to block adult, gambling, and aggressive landing creatives.
3. **Legal & Privacy**: Update `/privacy` and `/terms` to disclose third-party cookie usage and Google/Adsterra tracking.
4. **Mobile Verification**: Ensure zero layout shift on 320px viewport devices during ad loading.
5. **Signed Document URLs**: Ensure Supabase storage token expiration is tuned to 15m (900s).
