I'm finishing the log analysis: bot traffic share, per-page Supabase calls and response times. Then I'll write the fix plan.

## What the logs show about the failed upload

The export covers 09:25 to 09:50 UTC (124 log lines, 36 requests). Only one visitor tried to upload, and I traced that visit. All times below are UTC; 09:49 UTC is 3:19 PM IST.

| Time | Request | Result |
|---|---|---|
| 09:49:17 | `POST /api/check-duplicate` | 200, Supabase hash lookup took 389 ms |
| 09:49:18 | `POST /api/get-upload-signature` | 200, took 7 ms |
| 09:49:18 | `GET /upload` | **413**, with no function invocation, duration or log line |

Here is what I can say, and what I can't:

- **Your Flask code never ran for the 413.** Every successful request has a duration, a memory reading and an invocation id, and this one has none. Vercel rejected it before your app saw it.
- **After the signature, no save request ever reached your server.** There's no insert and no "save document" call, so no database record was created. That matches "file not uploaded".
- **A 413 on a GET with no body is unusual.** I can't tell the cause from logs alone. The two likeliest are a response over Vercel's size limit, or a fallback in your JavaScript that sends the file through Flask. The log method may also be unreliable here, since this entry has little detail.
- **My earlier guess that the file probably reached Cloudinary was unsupported.** The upload goes browser to Cloudinary directly, so it never appears in these logs. I can't tell whether it happened.

Three quick checks will settle it:
1. Open DevTools, go to Network, and repeat the upload. Find the request that returns 413 and note its method, URL, request size and response size.
2. Check the Cloudinary media library for anything around 09:49 UTC. Also check your Cloudinary plan's maximum file size, since an oversized file would fail there with Cloudinary's own error.
3. In Supabase, search `documents` for `file_hash = 2e0f5d74ab2817cbfebc3f2f7a83a20ba48ab50eeaf54e39ac0427092b142c05`. If a row exists, the duplicate check may be what blocked the upload.

## Where your server load actually comes from

- **At least 26 of 36 requests (72%) are crawlers.** That's 9 from Facebook, 8 from Semrush, 5 from Google and AdsBot, 3 from Amazonbot and 1 from Bing. Facebook hit your home page 9 times in 25 minutes.
- **All 36 requests were cache MISS.** Each home-page hit makes 3 to 4 Supabase calls and takes 337 to 1,959 ms.
- **The redirect handlers are slow.** `/resources/<id>` and `/resources/legacy-redirect-<id>` took 911 and 1,016 ms just to send a redirect, because they query Supabase to build the slug.
- **Bots hit the login wall.** Amazonbot, Bing and Googlebot are redirected to `/login` on resource pages, so each visit costs a database query and two redirects and produces nothing indexable.
- **The scheduler fell behind 14 times in 25 minutes.** The search indexer was late by up to 1 minute 32 seconds, and upload notifications by 2 minutes.
- **Memory is fine.** The function peaked at about 284 MB of its 2,048 MB, so this is a request-volume and latency problem, not a memory one.

From the earlier log, the college page also runs `select=id` on `documents` and `subjects` just to count rows, which downloads every ID.

## The plan

I haven't seen your code, so adapt the snippets to your structure.

### Phase 0: today, about an hour, low risk

**1. Block junk crawlers.** Add a Vercel Firewall rule, or `robots.txt` entries, for SemrushBot and similar SEO scrapers. Semrush respects `robots.txt`, but Facebook and AdsBot may not. Check which firewall features your Vercel plan includes.
```
User-agent: SemrushBot
Disallow: /
User-agent: AhrefsBot
Disallow: /
User-agent: *
Disallow: /api/
Disallow: /login
```

**2. Cache logged-out pages at the CDN.**
```python
@app.after_request
def cache_public(resp):
    if (request.method == "GET" and resp.status_code == 200
            and not session.get("user_id")
            and request.path in ("/", ) or request.path.startswith(("/college/", "/subject/"))):
        resp.headers["Cache-Control"] = "public, s-maxage=300, stale-while-revalidate=600"
    return resp
```
Caution: only do this if those pages contain nothing user-specific (name, CSRF token, notification count). If they do, cache the data in step 3 instead of the page.

**3. Cache reference data in memory.** Colleges, departments, subjects and `scoring_config` rarely change.
```python
from cachetools import TTLCache, cached
_ref = TTLCache(maxsize=64, ttl=600)

@cached(_ref)
def get_colleges():
    return supabase.table("colleges").select("*").order("name").execute().data
```
Do the same for departments and `scoring_config`. This cuts the home page from 4 Supabase calls to about 1.

**4. Count without downloading rows.**
```python
supabase.table("documents").select("id", count="exact", head=True)\
    .eq("college_id", cid).eq("department_id", did).execute().count
```

### Phase 1: this week, fix the upload and the redirects

**Upload.** The correct flow is: browser hashes the file, calls `check-duplicate`, calls `get-upload-signature`, uploads **directly to Cloudinary**, then sends Flask only a small JSON (`public_id`, `url`, title, subject). Verify that no code path sends the file to Flask. Then:
- Show the user a clear error when any step fails, instead of failing silently.
- Log each step in Flask, including the Cloudinary `public_id`.
- Use Cloudinary's chunked upload for large PDFs.
- Retry the save step if it fails, so an uploaded file isn't orphaned.

**Redirects.**
- Store the slug in the `documents` table, or cache id-to-slug, so legacy and canonical redirects don't query Supabase.
- Use canonical `/resources/<slug>-<id>` links everywhere, including the sitemap.
- For logged-out visitors, redirect straight to `/login?next=<canonical>` in one hop, and never set `next` to a login URL.

**Public previews (your decision).** Show a public preview of each resource (title, subject, description) with the download behind login. Search engines can then index it, and it's cacheable. If you'd rather keep everything private, disallow `/resource/` and `/resources/` in `robots.txt` so bots stop spending queries there.

### Phase 2: next 1 to 2 weeks, fix the scheduler and move off serverless

- **Move to the Oracle VM** with gunicorn (1 worker), systemd and nginx, as in my earlier steps. The scheduler then runs on time because the process stays alive, the in-memory cache persists, and there are no cold starts.
- **Add nginx micro-caching** for anonymous pages:
```nginx
proxy_cache_path /var/cache/nginx keys_zone=pages:10m max_size=200m inactive=10m;
location / {
    proxy_cache pages;
    proxy_cache_valid 200 60s;
    proxy_cache_bypass $cookie_session;
    proxy_no_cache $cookie_session;
    proxy_pass http://127.0.0.1:8000;
}
```
Replace `session` with your real session cookie name.
- **Set `client_max_body_size 50m;`** so nginx's 1 MB default doesn't cause its own 413.
- **Replace the 2-minute search-index polling** with an event: when a document is approved, call the indexer from a Supabase database webhook or `pg_cron`. The indexer runs only when there's work.
- If you stay on Vercel, Vercel Cron frequency depends on your plan, so a 2-minute job may need a paid plan. Check their docs.

### Phase 3: ongoing

- Add indexes: `documents(file_hash)`, `documents(status, created_at desc)` and `documents(college_id, department_id, created_at desc)`.
- Poll `/api/my-notifications` less often (every 60 seconds, paused when the tab is hidden), or use Supabase Realtime, which you already have installed.
- Add `og:` tags and a cached response for Facebook's crawler on shared pages.

## How to know it worked

I haven't measured any of these gains, so treat the improvements as expected, not guaranteed. Track these before and after:
- **Cache HIT rate** on `/`, which is 0% now.
- **Home page response time**, currently 337 to 1,959 ms.
- **Supabase calls per page view**, currently 3 to 5.
- **Missed-job warnings**, currently 14 per 25 minutes, with a target of 0.
- **Upload success rate**, which you can log at each step.

To pin down the 413, can you paste the JavaScript that runs after `get-upload-signature` returns (the code that uploads to Cloudinary and then calls your server), or tell me what the Network tab shows for the 413 request? With that I can find the exact line and write the fix.