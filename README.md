# AbhiHub — Engineering Study Platform & AI Assistant

AbhiHub is a student-driven academic platform offering verified semester examination papers, topper handwritten notes, and an AI study companion (Tarika) running serverless on Vercel Python compute.

---

## Architecture & Load-Aware Serverless Infrastructure

1. **Fluid Active CPU Budgeting**:
   - Monitored per-request active thread CPU (`time.thread_time()`) written atomically to daily Redis keys (`budget:cpu:YYYY-MM-DD`).
   - Hysteresis load states: **Green** (<60%), **Yellow** (60%–85%), **Red** (>85%, exits at $\le 75\%$).
   - Under Red load, document search degrades from `rapidfuzz` fuzzy matching to fast prefix/exact matching without queuing.
2. **Serverless AI Queue**:
   - Token bucket rate limiter: max 15 requests/minute.
   - Daily free AI pool cap: 900 queries/day (reserving 100 for emergencies).
   - Single-use atomic tickets (`ticket:ai:<id>`, 90s TTL) consumed via `GETDEL`.
   - Ghost user cleanup: 30s heartbeat eviction.
3. **Multi-Level Caching**:
   - OCR text extraction cached per `doc_id` (`cache:ocr:<doc_id>`).
   - Search query normalization cached in Redis (`cache:search:<hash>`, TTL 2h).
   - Know-Me asset CDN render caching (`cache:know_me:<wall_id>`, TTL 7d).
   - Question/document short-TTL caching (`cache:ai:<doc_id>:<hash>`, TTL 30m).

---

## Important Notice: Vercel Pro Upgrade & Commercial Compliance

> [!WARNING]
> **Vercel Hobby is strictly non-commercial.**
> Payments (`FEATURE_PAYMENTS`) and advertisements (`FEATURE_ADS`) are commercial use.
> Both flags are built behind feature toggles and **default to OFF (`false`)**.
> 
> **You MUST upgrade your Vercel account from Hobby to Vercel Pro before enabling either `FEATURE_PAYMENTS=true` or `FEATURE_ADS=true` in production.**

### Pre-Launch Upgrade Checklist:
- [ ] Upgrade project subscription to **Vercel Pro** in Vercel Dashboard.
- [ ] Set `FEATURE_PAYMENTS=true` in Vercel Environment Variables.
- [ ] Set `FEATURE_ADS=true` in Vercel Environment Variables.
- [ ] Configure `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET`.
- [ ] Set `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`.
- [ ] Verify Adsterra category filters to prohibit gambling, adult, and malware creatives.
- [ ] Verify Privacy Policy reflects ad network and telemetry cookies.
- [ ] Test queue waiting screen and payment checkout on physical 320px mobile devices.

---

## Premium Plans

| Plan | Price | Duration | Entitlements |
|---|---|---|---|
| **Day Pass** | ₹29 | 24 Hours | Instant AI, No Queue, No Ads, Fast OCR (40/day), 15m Signed PDF URLs |
| **Exam Sprint** | ₹79 | 7 Days | Full exam cram access, Paid LLM fallback, Unmetered viewing |
| **Semester Pro** | ₹199 | 6 Months | Complete semester pass, 30 AI queries/day (400/month fair-use) |
