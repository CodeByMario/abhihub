/**
 * DEPRECATED: This service worker has been consolidated into the unified root service worker /sw.js.
 * Unregisters any existing registrations of this legacy file to ensure zero cache conflicts.
 */
self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (names) {
            return Promise.all(
                names.filter(function (n) { return n.startsWith('abhihub-v1'); }).map(function (n) { return caches.delete(n); })
            );
        }).then(function () {
            return self.registration.unregister();
        })
    );
});
