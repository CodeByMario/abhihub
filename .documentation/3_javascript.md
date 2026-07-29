# JavaScript Documentation — AbhiHub

## JS Architecture

AbhiHub uses **vanilla JavaScript** (no framework). Scripts are loaded per-page via `<script>` tags in templates. The master layout (`p_struct.html`) exposes globals consumed by all page scripts.

---

## Global Objects (set in `p_struct.html`)

```js
window.__CURRENT_USER__   // { uid, email, name, provider }
window.safeGtag(cmd, name, params)   // GA4 deduplication wrapper
window.trackEvent(eventName, data)   // GA4 shorthand
window.AbhiHubTracking               // Analytics methods object
```

---

## JS File Map

### Root Static (`static/`)

| File | Purpose |
|---|---|
| `index.js` | App entry/init |
| `scripts.js` | Shared utilities |
| `navbar.js` | Navbar behavior |
| `login-auth.js` | Login auth flow |
| `firebase-config.js` | Firebase client config |
| `supabase-config.js` | Supabase client config |
| `aes_decrypt.js` | AES file decryption |
| `encrypted_pdf_viewer.js` | Encrypted PDF viewer |
| `encryptedFileManager.js` | Encrypted file manager |

### Page-Specific (`static/js/`)

| File | Page / Feature |
|---|---|
| `p_index.js` | Dashboard |
| `p_landing.js` | Landing page |
| `p_login.js` | Login page |
| `access-gates.js` | Access control gates |
| `ad-manager.js` | Ad display manager |
| `admin-dashboard.js` | Admin dashboard |
| `analytics-helper.js` | Analytics utilities |
| `bulk_upload.js` | Bulk file upload |
| `carousel-personalization.js` | Personalized carousel |
| `file-history-tracker.js` | File access history tracking |
| `know-me.js` | Know Me / MemoryWall |
| `overlay-manager.js` | Overlay/modal management |
| `previously-accessed-files.js` | Previously accessed files panel |
| `push-notifications.js` | Web push notifications |
| `pwa-install.js` | PWA install prompt |
| `security.js` | Client-side security checks |

### Premium Section (`static/premium/js/`)

| File | Purpose |
|---|---|
| `script.js` | Premium section main script |
| `interactions.js` | Like/bookmark/comment interactions |
| `verification.js` | Document verification UI |
| `search-worker.js` | Search web worker |
| `store_room.js` | Store room feature |

---

## Key Patterns

### API Calls
All API calls use `fetch()` with JSON body:

```js
const res = await fetch('/api/endpoint', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ key: value })
});
const data = await res.json();
```

### Analytics Tracking
```js
// Tracking an event
window.trackEvent('file_view', { file_id: id, subject: name });

// Feature-specific tracker
window.AbhiHubTracking.trackFileView(fileId, fileName);
window.AbhiHubTracking.trackUpload(fileType, college);
window.AbhiHubTracking.trackShare(method, fileId);
```

### Service Worker (`static/sw.js`)
- Handles PWA caching strategy
- Manages offline fallback (`templates/offline.html`)
- Push notification event handler

---

## Firebase Client (`firebase-config.js`)
- Used for: Authentication fallback, Signature image storage
- Bucket: `abhi-hub.appspot.com`

## Supabase Client (`supabase-config.js`)
- Used for: Client-side auth session checks
- Schema: `abhihub`

---

## Search (`static/search.json`)
- Pre-built search index for client-side search
- Consumed by `search-worker.js` (web worker)

---

## PWA
- Manifest: `static/manifest.json`
- Icons: `static/images/`, `icons/android/`
- Install prompt handled by `pwa-install.js` + `pwa-install.css`
