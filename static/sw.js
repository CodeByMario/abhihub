/**
 * AbhiHub Service Worker
 * Production-ready PWA service worker with:
 * - Offline-first caching strategy
 * - Image/PDF runtime caching
 * - Upload/auth exclusion
 * - Widget update support
 * - Background sync
 */

const CACHE_VERSION = 'v2.0.2';
const CACHE_NAME = `abhihub-${CACHE_VERSION}`;
const STATIC_CACHE = `abhihub-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `abhihub-dynamic-${CACHE_VERSION}`;
const IMAGE_CACHE = `abhihub-images-${CACHE_VERSION}`;

// Core files to cache immediately on install
const PRECACHE_URLS = [
  '/',
  '/premium',
  '/premium/',
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
  '/static/widget/data.json'
];

// Paths that should NEVER be cached (security-sensitive)
const NEVER_CACHE_PATTERNS = [
  /\/api\//,
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

/**
 * Check if URL is an image
 */
function isImageUrl(url) {
  const imageExts = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico'];
  return imageExts.some(ext => url.pathname.toLowerCase().endsWith(ext));
}

/**
 * Check if URL is a PDF
 */
function isPdfUrl(url) {
  return url.pathname.toLowerCase().endsWith('.pdf');
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

  // Skip cross-origin requests
  if (url.origin !== self.location.origin) {
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

  // Handle images with stale-while-revalidate
  if (isImageUrl(url)) {
    event.respondWith(handleImageRequest(request));
    return;
  }

  // Handle PDFs with cache-first strategy
  if (isPdfUrl(url)) {
    event.respondWith(handlePdfRequest(request));
    return;
  }

  // Handle navigation requests
  if (request.mode === 'navigate') {
    event.respondWith(handleNavigationRequest(request));
    return;
  }

  // Handle other requests with stale-while-revalidate
  event.respondWith(handleStandardRequest(request));
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
 * Handle navigation requests with network-first fallback to cache
 */
async function handleNavigationRequest(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      // Cache successful navigation responses
      const cache = await caches.open(DYNAMIC_CACHE);
      await cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    // Network failed, try cache
    const cachedResponse = await caches.match(request, { ignoreSearch: true });
    if (cachedResponse) {
      return cachedResponse;
    }

    // Return offline page
    const offlineResponse = await caches.match('/offline');
    if (offlineResponse) {
      return offlineResponse;
    }

    // Last resort: basic offline message
    return new Response(
      '<!DOCTYPE html><html><body><h1>Offline</h1><p>Please check your connection.</p></body></html>',
      { headers: { 'Content-Type': 'text/html' } }
    );
  }
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

  // Start background fetch
  const fetchPromise = fetch(request).then(async (networkResponse) => {
    if (networkResponse.ok && isCacheableUrl(url)) {
      await cache.put(request, networkResponse.clone());
      await limitCacheSize(cacheName, MAX_DYNAMIC_CACHE_ITEMS);
    }
    return networkResponse;
  }).catch(() => null);

  // Return cache immediately if available
  if (cachedResponse) {
    return cachedResponse;
  }

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
      clients.openWindow('/premium')
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
    url: '/premium',
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
  const urlToOpen = event.notification.data?.url || '/premium';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Check if app window is already open
        for (const client of clientList) {
          if (client.url.includes('/premium') && 'focus' in client) {
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
