/**
 * AbhiHub Service Worker
 * Production-ready PWA service worker with:
 * - Offline-first caching strategy
 * - Encrypted PDF caching (AES-GCM, 24h TTL)
 * - Image runtime caching
 * - Upload/auth exclusion
 * - Widget update support
 * - Background sync
 */

const CACHE_VERSION = 'v2.0.4';
const CACHE_NAME = `abhihub-${CACHE_VERSION}`;
const STATIC_CACHE = `abhihub-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `abhihub-dynamic-${CACHE_VERSION}`;
const IMAGE_CACHE = `abhihub-images-${CACHE_VERSION}`;

// ==================== ENCRYPTED PDF CACHE ====================
const PDF_IDB_NAME = 'abhihub-pdf-cache';
const PDF_IDB_STORE = 'encrypted-pdfs';
const PDF_CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

/** Open (or create) the PDF IndexedDB */
function openPdfDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(PDF_IDB_NAME, 1);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(PDF_IDB_STORE)) {
        db.createObjectStore(PDF_IDB_STORE, { keyPath: 'key' });
      }
    };
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = (e) => reject(e.target.error);
  });
}

/** Get or create a persistent AES-GCM CryptoKey stored in IDB */
async function getOrCreateCryptoKey(db) {
  const tx = db.transaction(PDF_IDB_STORE, 'readwrite');
  const store = tx.objectStore(PDF_IDB_STORE);
  const existing = await new Promise((res) => {
    const r = store.get('__cryptokey__');
    r.onsuccess = () => res(r.result);
    r.onerror = () => res(null);
  });
  if (existing) {
    return crypto.subtle.importKey('raw', existing.keyData, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
  }
  const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']);
  const raw = await crypto.subtle.exportKey('raw', key);
  await new Promise((res, rej) => {
    const r = store.put({ key: '__cryptokey__', keyData: raw });
    r.onsuccess = res; r.onerror = rej;
  });
  return key;
}

/** Encrypt ArrayBuffer -> { iv, data } */
async function encryptPdf(cryptoKey, buffer) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, cryptoKey, buffer);
  return { iv, data };
}

/** Decrypt { iv, data } -> ArrayBuffer */
async function decryptPdf(cryptoKey, iv, data) {
  return crypto.subtle.decrypt({ name: 'AES-GCM', iv }, cryptoKey, data);
}

/** Store encrypted PDF in IDB with timestamp */
async function storePdfInIdb(db, cacheKey, encryptedPayload, contentType) {
  const tx = db.transaction(PDF_IDB_STORE, 'readwrite');
  const store = tx.objectStore(PDF_IDB_STORE);
  await new Promise((res, rej) => {
    const r = store.put({
      key: cacheKey,
      iv: encryptedPayload.iv,
      data: encryptedPayload.data,
      contentType,
      cachedAt: Date.now()
    });
    r.onsuccess = res; r.onerror = rej;
  });
}

/** Retrieve and validate PDF from IDB */
async function getPdfFromIdb(db, cacheKey) {
  return new Promise((res) => {
    const tx = db.transaction(PDF_IDB_STORE, 'readonly');
    const r = tx.objectStore(PDF_IDB_STORE).get(cacheKey);
    r.onsuccess = () => res(r.result || null);
    r.onerror = () => res(null);
  });
}

/** Delete a single PDF entry from IDB */
async function deletePdfFromIdb(db, cacheKey) {
  const tx = db.transaction(PDF_IDB_STORE, 'readwrite');
  tx.objectStore(PDF_IDB_STORE).delete(cacheKey);
}

/** Evict all IDB PDF entries older than TTL */
async function evictExpiredPdfs(db) {
  const now = Date.now();
  const tx = db.transaction(PDF_IDB_STORE, 'readwrite');
  const store = tx.objectStore(PDF_IDB_STORE);
  const req = store.openCursor();
  req.onsuccess = (e) => {
    const cursor = e.target.result;
    if (!cursor) return;
    const entry = cursor.value;
    if (entry.key !== '__cryptokey__' && entry.cachedAt && (now - entry.cachedAt) > PDF_CACHE_TTL_MS) {
      cursor.delete();
    }
    cursor.continue();
  };
}

/**
 * Fetch and cache a cross-origin PDF (Firebase/Cloudinary signed URL)
 * Encrypts bytes into IDB. Returns decrypted Response.
 */
async function handleEncryptedPdfFetch(originalUrl) {
  const db = await openPdfDb();
  const cryptoKey = await getOrCreateCryptoKey(db);
  const cacheKey = originalUrl; // use full URL as key

  // Evict stale entries opportunistically
  evictExpiredPdfs(db);

  // Check IDB cache
  const cached = await getPdfFromIdb(db, cacheKey);
  if (cached) {
    if ((Date.now() - cached.cachedAt) < PDF_CACHE_TTL_MS) {
      try {
        const decrypted = await decryptPdf(cryptoKey, cached.iv, cached.data);
        return new Response(decrypted, {
          headers: { 'Content-Type': cached.contentType || 'application/pdf' }
        });
      } catch {
        await deletePdfFromIdb(db, cacheKey); // corrupt entry
      }
    } else {
      await deletePdfFromIdb(db, cacheKey); // expired
    }
  }

  // Fetch fresh
  let networkResponse;
  try {
    networkResponse = await fetch(originalUrl, { mode: 'cors' });
  } catch {
    return new Response('PDF unavailable offline', { status: 503 });
  }

  if (!networkResponse.ok) return networkResponse;

  const buffer = await networkResponse.clone().arrayBuffer();
  const contentType = networkResponse.headers.get('Content-Type') || 'application/octet-stream';
  const encrypted = await encryptPdf(cryptoKey, buffer);
  await storePdfInIdb(db, cacheKey, encrypted, contentType);

  return new Response(buffer, { headers: { 'Content-Type': contentType } });
}
// Alias for clarity — handles ALL file types, not just PDFs
const handleEncryptedFileFetch = handleEncryptedPdfFetch;
// ==================== END ENCRYPTED FILE CACHE ====================

// Core files to cache immediately on install
const PRECACHE_URLS = [
  '/',
  '/dashboard',
  '/dashboard/',
  '/login',
  '/signup',
  '/offline',
  '/static/manifest.json',
  '/static/css/abhihub-theme.css',
  '/static/premium/css/style.css',
  '/static/images/android-chrome-192x192.png',
  '/static/images/android-chrome-512x512.png',
  '/static/images/apple-touch-icon.png',
  '/static/images/logo.png',
  '/static/widget/template.json',
  '/static/widget/data.json',
  // Key app pages — cached on install for offline access
  '/dashboard',
  '/account',
  '/profile',
  '/dashboard',
  '/dashboard/',
];

// Paths that should NEVER be cached (security-sensitive)
const NEVER_CACHE_PATTERNS = [
  /\/api\/(?!profile-status|view-doc)/,  // block all /api/ except profile-status and view-doc
  /\/auth\//,
  /\/login/,
  /\/logout/,
  /\/signup/,
  /\/upload/,
  /\/admin/,
  /\/session/,
  /\/password/,
  /\/token/,
  /\/premium\/share-receiver/
];

// Lightweight API responses to cache with stale-while-revalidate (short TTL)
const CACHEABLE_API_PATHS = [
  '/api/profile-status',
];
const API_CACHE = `abhihub-api-${CACHE_VERSION}`;
const API_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

// File extensions eligible for caching
const CACHEABLE_EXTENSIONS = [
  '.html', '.css', '.js', '.json',
  '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico',
  '.woff', '.woff2', '.ttf', '.eot',
  '.pdf'
];

// Maximum cache sizes
const MAX_DYNAMIC_CACHE_ITEMS = 50;
const MAX_IMAGE_CACHE_ITEMS = 100;

/**
 * Check if a request should never be cached
 */
function shouldNeverCache(url) {
  return NEVER_CACHE_PATTERNS.some(pattern => pattern.test(url.pathname));
}

/**
 * Check if a URL is cacheable based on extension
 */
function isCacheableUrl(url) {
  const pathname = url.pathname.toLowerCase();
  return CACHEABLE_EXTENSIONS.some(ext => pathname.endsWith(ext));
}

// All file types to cache for user access
const USER_FILE_EXTS = new Set([
  '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico',
  '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt',
  '.zip', '.rar', '.7z'
]);

/**
 * Check if URL is an image
 */
function isImageUrl(url) {
  const imageExts = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico'];
  return imageExts.some(ext => url.pathname.toLowerCase().endsWith(ext));
}

/**
 * Check if URL is a user-accessible file (any type we cache)
 */
function isUserFile(url) {
  const p = url.pathname.toLowerCase();
  return Array.from(USER_FILE_EXTS).some(ext => p.endsWith(ext));
}

/**
 * Check if cross-origin URL is a Firebase/Cloudinary file
 */
function isCrossOriginFile(url) {
  // Cloudinary: res.cloudinary.com, Firebase Storage, or signed URL patterns
  return isUserFile(url)
    || url.hostname.includes('cloudinary.com')
    || url.hostname.includes('firebasestorage.googleapis.com')
    || url.hostname.includes('storage.googleapis.com')
    || url.searchParams.has('alt')
    || url.pathname.includes('/object/');
}

/**
 * Limit cache size by removing oldest entries
 */
async function limitCacheSize(cacheName, maxItems) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if (keys.length > maxItems) {
    // Remove oldest entries (first in cache)
    const deleteCount = keys.length - maxItems;
    for (let i = 0; i < deleteCount; i++) {
      await cache.delete(keys[i]);
    }
  }
}

// ==================== INSTALL EVENT ====================
self.addEventListener('install', (event) => {
  console.log('[SW] Installing version:', CACHE_VERSION);

  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Precaching core assets');
        // Use addAll with error handling for individual fails
        return Promise.allSettled(
          PRECACHE_URLS.map(url =>
            cache.add(url).catch(err => {
              console.warn(`[SW] Failed to cache: ${url}`, err);
            })
          )
        );
      })
      .then(() => {
        console.log('[SW] Install complete');
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error('[SW] Install failed:', error);
      })
  );
});

// ==================== ACTIVATE EVENT ====================
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating version:', CACHE_VERSION);

  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => {
              // Delete old caches that don't match current version
              return name.startsWith('abhihub-') &&
                name !== STATIC_CACHE &&
                name !== DYNAMIC_CACHE &&
                name !== IMAGE_CACHE;
            })
            .map((name) => {
              console.log('[SW] Deleting old cache:', name);
              return caches.delete(name);
            })
        );
      })
      .then(() => {
        console.log('[SW] Activation complete');
        return self.clients.claim();
      })
  );
});

// ==================== FETCH EVENT ====================
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests (POST, PUT, DELETE should never be cached)
  if (request.method !== 'GET') {
    return;
  }

  // Intercept cross-origin file requests (Firebase/Cloudinary signed URLs — all types)
  if (url.origin !== self.location.origin) {
    if (isCrossOriginFile(url)) {
      event.respondWith(handleEncryptedFileFetch(request.url));
    }
    return;
  }

  // Skip chrome extensions and dev tools
  if (url.protocol === 'chrome-extension:' || url.pathname.includes('__')) {
    return;
  }

  // Never cache security-sensitive endpoints
  if (shouldNeverCache(url)) {
    event.respondWith(fetch(request));
    return;
  }

  // Cacheable API endpoints (profile-status etc.) — stale-while-revalidate
  if (CACHEABLE_API_PATHS.some(p => url.pathname === p)) {
    event.respondWith(handleCacheableApiRequest(request));
    return;
  }

  // All same-origin user files (images, PDFs, docs) → encrypted IDB cache-first
  // EXCLUDE /api/view-doc/ — these are proxied through Flask and should not be cached by SW
  // PDF.js viewer fetches them via fetch() and requires proper streaming + headers
  if (isUserFile(url) && !url.pathname.startsWith('/api/view-doc/')) {
    event.respondWith(handleEncryptedFileFetch(request.url));
    return;
  }

  // Handle navigation requests
  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        // Try navigation preload first
        try {
          const preloadResponse = await event.preloadResponse;
          if (preloadResponse) return preloadResponse;
        } catch {}
        return handleNavigationRequest(request);
      })()
    );
    return;
  }

  // Handle other requests with stale-while-revalidate
  // /api/view-doc/ image endpoints: bypass SW cache entirely, go direct to network.
  // These are proxied by Flask and carry no file extension, so the generic cache
  // path can serve stale/broken responses and cause invisible images.
  if (url.pathname.startsWith('/api/view-doc/') && isImageUrl(url)) {
    event.respondWith(fetch(request));
    return;
  }

  event.respondWith(
    (async () => {
      if (url.pathname.endsWith('.js') || url.pathname.endsWith('.mjs')) {
        const cache = await caches.open(DYNAMIC_CACHE);
        const cachedResponse = await cache.match(request, { ignoreSearch: true });
        if (cachedResponse) {
          const cachedType = cachedResponse.headers.get('Content-Type') || '';
          if (cachedType.includes('text/html') || !cachedType.includes('javascript')) {
            await cache.delete(request);
            return fetch(request);
          }
        }
      }
      return handleStandardRequest(request);
    })()
  );
});

/**
 * Handle image requests with stale-while-revalidate
 */
async function handleImageRequest(request) {
  const cache = await caches.open(IMAGE_CACHE);
  const cachedResponse = await cache.match(request, { ignoreSearch: true });

  // Start network fetch in background
  const networkFetch = fetch(request).then(async (networkResponse) => {
    if (networkResponse.ok) {
      await cache.put(request, networkResponse.clone());
      await limitCacheSize(IMAGE_CACHE, MAX_IMAGE_CACHE_ITEMS);
    }
    return networkResponse;
  }).catch(() => null);

  // Return cached immediately if available
  if (cachedResponse) {
    return cachedResponse;
  }

  // Wait for network if no cache
  const response = await networkFetch;
  if (response) {
    return response;
  }

  // Return placeholder for failed image loads
  return new Response('', { status: 404, statusText: 'Image not found' });
}

/**
 * Handle PDF requests with cache-first strategy
 */
async function handlePdfRequest(request) {
  const cache = await caches.open(DYNAMIC_CACHE);
  const cachedResponse = await cache.match(request, { ignoreSearch: true });

  if (cachedResponse) {
    // Update cache in background
    fetch(request).then(async (networkResponse) => {
      if (networkResponse.ok) {
        await cache.put(request, networkResponse.clone());
      }
    }).catch(() => { });
    return cachedResponse;
  }

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      await cache.put(request, networkResponse.clone());
      await limitCacheSize(DYNAMIC_CACHE, MAX_DYNAMIC_CACHE_ITEMS);
    }
    return networkResponse;
  } catch (error) {
    return new Response('PDF not available offline', {
      status: 503,
      statusText: 'Service Unavailable',
      headers: { 'Content-Type': 'text/plain' }
    });
  }
}

/**
 * Handle navigation requests — stale-while-revalidate for offline-first UX.
 * Serves cached page immediately, refreshes cache in background.
 */
async function handleNavigationRequest(request) {
  const cache = await caches.open(DYNAMIC_CACHE);
  const cachedResponse = await cache.match(request, { ignoreSearch: true });

  // Kick off network refresh in background
  const networkFetch = fetch(request).then(async (networkResponse) => {
    if (networkResponse.ok) {
      await cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  }).catch(() => null);

  // Serve cached immediately if available (instant load)
  if (cachedResponse) {
    // Safety: don't serve HTML for non-HTML requests
    const cachedType = cachedResponse.headers.get('Content-Type') || '';
    if (cachedType.includes('text/html')) {
      return cachedResponse;
    }
  }

  // No cache — wait for network
  const networkResponse = await networkFetch;
  if (networkResponse) return networkResponse;

  // Fully offline fallback
  const offlinePage = await caches.match('/offline');
  return offlinePage || new Response(
    `<!DOCTYPE html><html><head><title>Offline — AbhiHub</title><style>
      body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#0f172a;color:#e2e8f0;text-align:center;}
      .card{background:#1e293b;border-radius:16px;padding:2rem;max-width:360px;}
      h1{font-size:1.5rem;margin-bottom:.5rem;} p{color:#94a3b8;}
      a{display:inline-block;margin-top:1rem;padding:.7rem 1.5rem;background:#2563eb;color:#fff;border-radius:8px;text-decoration:none;}
    </style></head><body>
      <div class="card">
        <div style="font-size:3rem">📚</div>
        <h1>You're Offline</h1>
        <p>AbhiHub isn't available right now. Previously visited pages are still accessible.</p>
        <a href="/dashboard">Go to Dashboard</a>
      </div>
    </body></html>`,
    { headers: { 'Content-Type': 'text/html' } }
  );
}

/**
 * Stale-while-revalidate handler for lightweight cacheable API responses.
 */
async function handleCacheableApiRequest(request) {
  const cache = await caches.open(API_CACHE);
  const cacheKey = request.url;
  const cachedResponse = await cache.match(cacheKey);

  // Refresh in background
  const networkFetch = fetch(request, { credentials: 'same-origin' }).then(async (networkResponse) => {
    if (networkResponse.ok) {
      await cache.put(cacheKey, networkResponse.clone());
    }
    return networkResponse;
  }).catch(() => null);

  // Serve stale immediately if available
  if (cachedResponse) {
    return cachedResponse;
  }

  // No cache yet — wait for network
  const networkResponse = await networkFetch;
  return networkResponse || new Response(JSON.stringify({ profile_completed: false }), {
    headers: { 'Content-Type': 'application/json' }
  });
}

/**
 * Handle standard requests with stale-while-revalidate
 */
async function handleStandardRequest(request) {
  const url = new URL(request.url);

  // Determine which cache to use
  const cacheName = isCacheableUrl(url) ? DYNAMIC_CACHE : STATIC_CACHE;
  const cache = await caches.open(cacheName);
  const cachedResponse = await cache.match(request, { ignoreSearch: true });

  // Safety: verify cached response content type matches expected type
  if (cachedResponse) {
    const cachedType = cachedResponse.headers.get('Content-Type') || '';
    const isJsOrCss = url.pathname.endsWith('.js') || url.pathname.endsWith('.css');
    if (isJsOrCss && cachedType.includes('text/html')) {
      // Don't serve HTML for JS/CSS requests — delete bad cache and fetch fresh
      await cache.delete(request);
      return fetch(request);
    } else {
      // Start background fetch
      const fetchPromise = fetch(request).then(async (networkResponse) => {
        if (networkResponse.ok && isCacheableUrl(url)) {
          await cache.put(request, networkResponse.clone());
          await limitCacheSize(cacheName, MAX_DYNAMIC_CACHE_ITEMS);
        }
        return networkResponse;
      }).catch(() => null);

      // If this is a non-cacheable request (e.g. /api/view-doc/), always go network
      if (!isCacheableUrl(url)) {
        return fetch(request);
      }

      return cachedResponse;
    }
  }

  // Start background fetch
  const fetchPromise = fetch(request).then(async (networkResponse) => {
    if (networkResponse.ok && isCacheableUrl(url)) {
      await cache.put(request, networkResponse.clone());
      await limitCacheSize(cacheName, MAX_DYNAMIC_CACHE_ITEMS);
    }
    return networkResponse;
  }).catch(() => null);

  // Wait for network
  const networkResponse = await fetchPromise;
  if (networkResponse) {
    return networkResponse;
  }

  // Fallback for CSS/JS
  return new Response('', { status: 404 });
}

// ==================== MESSAGE EVENT ====================
self.addEventListener('message', (event) => {
  if (event.data) {
    switch (event.data.type) {
      case 'SKIP_WAITING':
        self.skipWaiting();
        break;

      case 'CLEAR_CACHE':
        caches.keys().then(names => {
          names.forEach(name => caches.delete(name));
        });
        break;

      case 'UPDATE_WIDGET':
        updateWidgetData(event.data.data);
        break;
    }
  }
});

// ==================== BACKGROUND SYNC ====================
self.addEventListener('sync', (event) => {
  console.log('[SW] Sync event:', event.tag);

  switch (event.tag) {
    case 'sync-widget':
      event.waitUntil(syncWidgetData());
      break;
    case 'sync-offline-actions':
      event.waitUntil(syncOfflineActions());
      break;
  }
});

/**
 * Sync widget data from server
 */
async function syncWidgetData() {
  try {
    const response = await fetch('/api/widget-data');
    if (response.ok) {
      const data = await response.json();
      await updateWidgetData(data);
    }
  } catch (error) {
    console.warn('[SW] Widget sync failed:', error);
  }
}

/**
 * Update widget data in cache
 */
async function updateWidgetData(data) {
  try {
    const cache = await caches.open(STATIC_CACHE);
    const response = new Response(JSON.stringify(data), {
      headers: { 'Content-Type': 'application/json' }
    });
    await cache.put('/static/widget/data.json', response);
    console.log('[SW] Widget data updated');
  } catch (error) {
    console.error('[SW] Widget update failed:', error);
  }
}

/**
 * Sync offline actions (placeholder for future queued actions)
 */
async function syncOfflineActions() {
  console.log('[SW] Syncing offline actions...');
  // Implement queued action sync here
  return Promise.resolve();
}

// ==================== PERIODIC SYNC ====================
self.addEventListener('periodicsync', (event) => {
  console.log('[SW] Periodic sync:', event.tag);

  if (event.tag === 'widget-update') {
    event.waitUntil(syncWidgetData());
  }
});

// ==================== WIDGET EVENTS ====================
// Handle widget install (experimental API)
self.addEventListener('widgetinstall', (event) => {
  console.log('[SW] Widget installed:', event.widget.definition.name);
  event.waitUntil(syncWidgetData());
});

// Handle widget uninstall
self.addEventListener('widgetuninstall', (event) => {
  console.log('[SW] Widget uninstalled:', event.widget.definition.name);
});

// Handle widget resume
self.addEventListener('widgetresume', (event) => {
  console.log('[SW] Widget resumed');
  event.waitUntil(syncWidgetData());
});

// Handle widget click
self.addEventListener('widgetclick', (event) => {
  console.log('[SW] Widget clicked:', event.action);

  if (event.action === 'open-app') {
    event.waitUntil(
      clients.openWindow('/dashboard')
    );
  }
});

console.log('[SW] Service Worker loaded - version:', CACHE_VERSION);

// ==================== PUSH NOTIFICATIONS ====================

/**
 * Handle incoming push notifications
 */
self.addEventListener('push', (event) => {
  console.log('[SW] Push received');

  let data = {
    title: 'AbhiHub',
    body: 'You have a new notification',
    icon: '/static/images/android-chrome-192x192.png',
    badge: '/static/images/favicon-32x32.png',
    url: '/dashboard',
    tag: 'abhihub-notification'
  };

  // Parse push data if available
  if (event.data) {
    try {
      const payload = event.data.json();
      data = { ...data, ...payload };
    } catch (e) {
      // If not JSON, use text
      data.body = event.data.text() || data.body;
    }
  }

  const options = {
    body: data.body,
    icon: data.icon,
    badge: data.badge,
    tag: data.tag,
    data: { url: data.url },
    vibrate: [100, 50, 100],
    requireInteraction: false,
    actions: [
      { action: 'open', title: 'Open' },
      { action: 'dismiss', title: 'Dismiss' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

/**
 * Handle notification click
 */
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked:', event.action);

  event.notification.close();

  // Handle actions
  if (event.action === 'dismiss') {
    return;
  }

  // Get URL from notification data or default to /premium
  const urlToOpen = event.notification.data?.url || '/dashboard';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Check if app window is already open
        for (const client of clientList) {
          if (client.url.includes('/dashboard') && 'focus' in client) {
            client.navigate(urlToOpen);
            return client.focus();
          }
        }
        // Open new window if not
        return clients.openWindow(urlToOpen);
      })
  );
});

/**
 * Handle notification close
 */
self.addEventListener('notificationclose', (event) => {
  console.log('[SW] Notification closed');
});
