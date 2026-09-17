/**
 * AbhiHub Service Worker
 * - Handles push notifications on laptop/desktop browsers
 * - Caches app shell for offline access (PWA)
 */
const CACHE_NAME = 'abhihub-v1';
const STATIC_ASSETS = [
    '/',
    '/static/manifest.json',
    '/static/images/android-chrome-192x192.png',
    '/static/images/apple-touch-icon.png',
    '/static/images/android-chrome-512x512.png'
];

// Install: cache the app shell
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        }).then(() => self.skipWaiting())
    );
});

// Activate: clean up old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch: network-first for HTML, cache-first for static assets
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Skip non-GET requests
    if (event.request.method !== 'GET') return;

    // Skip chrome-extension and other non-abhihub requests
    if (!url.origin.includes('abhihub')) return;

    // HTML pages: network-first, fallback to cache
    if (url.pathname.endsWith('/') || url.pathname.endsWith('.html')) {
        event.respondWith(
            fetch(event.request).then((response) => {
                const clone = response.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                return response;
            }).catch(() => caches.match(event.request).then((cached) => cached || new Response('Offline', { status: 503 })))
        );
        return;
    }

    // Static assets: cache-first
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(event.request).then((cached) => {
                return cached || fetch(event.request).then((response) => {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                    return response;
                });
            })
        );
        return;
    }
});

// Push: show notification when a push message arrives
self.addEventListener('push', (event) => {
    if (!event.data) return;

    let data;
    try {
        data = event.data.json();
    } catch (e) {
        data = { title: 'AbhiHub', body: event.data.text() };
    }

    const title = data.title || 'AbhiHub';
    const body = data.body || '';
    const icon = data.icon || '/static/images/android-chrome-192x192.png';
    const badge = data.badge || '/static/images/favicon-32x32.png';
    const url = data.url || '/dashboard';
    const tag = data.tag || 'abhihub-push';

    event.waitUntil(
        self.registration.showNotification(title, {
            body: body,
            icon: icon,
            badge: badge,
            tag: tag,
            data: { url: url },
            actions: [
                { action: 'open', title: 'Open' },
                { action: 'close', title: 'Close' }
            ]
        })
    );
});

// Notification click: open the app to the relevant URL
self.addEventListener('notificationclick', (event) => {
    event.notification.close();

    if (event.action === 'close') return;

    const url = event.notification.data && event.notification.data.url
        ? event.notification.data.url
        : '/dashboard';

    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
            // Try to focus existing window
            for (const client of clients) {
                if (client.url.includes(self.location.origin) && 'focus' in client) {
                    client.focus();
                    client.postMessage({ type: 'NOTIF_CLICK', url: url });
                    return;
                }
            }
            // Otherwise open new window
            return self.clients.openWindow(url);
        })
    );
});

// Handle messages from the page (e.g. notification badge update)
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'NOTIF_UPDATE') {
        // Page can request notification permission reminder, etc.
        console.log('[SW] Message from page:', event.data);
    }
});
