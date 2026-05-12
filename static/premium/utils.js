// Helper Functions
const utils = {
  // Network status check
  isOnline: () => navigator.onLine,

  // URL parsing
  getPathFromUrl: (url) => new URL(url).pathname,

  // Generate unique request ID
  generateRequestId: () => Math.random().toString(36).substring(7),

  // Retry mechanism with exponential backoff
  async retry(fn, retries = CONFIG.maxRetries) {
    for (let i = 0; i < retries; i++) {
      try {
        return await fn();
      } catch (error) {
        const waitTime = Math.min(
          CONFIG.maxBackoffPeriod,
          CONFIG.backoffPeriod * Math.pow(2, i)
        );
        await new Promise(resolve => setTimeout(resolve, waitTime));
        if (i === retries - 1) throw error;
      }
    }
  },

  // Check if URL is in scope
  isUrlInScope: (url) => {
    const path = utils.getPathFromUrl(url);
    return path.startsWith('/premium/') || 
           path.startsWith('/static/') || 
           STATIC_RESOURCES.includes(path);
  },

  // Extract file extension
  getFileExtension: (url) => {
    const filename = url.split('/').pop();
    return filename.includes('.') ? filename.split('.').pop().toLowerCase() : '';
  },

  // Check if request is for an API endpoint
  isApiRequest: (request) => {
    return request.url.includes('/api/') || 
           request.url.includes('/premium/search') ||
           request.headers.get('Accept')?.includes('application/json');
  },

  // Check if request is for a static resource
  isStaticResource: (request) => {
    const url = new URL(request.url);
    return STATIC_RESOURCES.includes(url.pathname) ||
           url.pathname.startsWith('/static/');
  },

  // Check if request is for a document
  isDocumentRequest: (request) => {
    const ext = utils.getFileExtension(request.url);
    return ['pdf', 'doc', 'docx', 'ppt', 'pptx'].includes(ext);
  },

  // Response handlers
  async responseHandlers(response, cacheName) {
    if (!response.ok) throw new Error('Network response was not ok');
    
    const clonedResponse = response.clone();
    const cache = await caches.open(cacheName);
    await cache.put(request, clonedResponse);
    
    return response;
  },

  // Background sync handlers
  async queueBackgroundSync(request) {
    const db = await this.getIndexedDB();
    const tx = db.transaction('sync-queue', 'readwrite');
    const store = tx.objectStore('sync-queue');
    
    await store.add({
      id: this.generateRequestId(),
      url: request.url,
      timestamp: Date.now(),
      method: request.method,
      headers: Array.from(request.headers.entries()),
      body: await request.clone().text()
    });
    
    return registration.sync.register('sync-pending-requests');
  },

  // IndexedDB operations
  async getIndexedDB() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('abhihub-offline', 1);
      
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
      
      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains('sync-queue')) {
          db.createObjectStore('sync-queue', { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains('user-data')) {
          db.createObjectStore('user-data', { keyPath: 'id' });
        }
      };
    });
  },

  // Cache management
  async clearOldCaches() {
    const cacheNames = await caches.keys();
    const validCacheSet = new Set(Object.values(CONFIG.cacheNames));
    
    return Promise.all(
      cacheNames.map(cacheName => {
        if (!validCacheSet.has(cacheName)) {
          return caches.delete(cacheName);
        }
      })
    );
  },

  // Resource preloading
  async preloadResources(resources, cacheName) {
    const cache = await caches.open(cacheName);
    return Promise.all(
      resources.map(async resource => {
        try {
          const response = await fetch(resource);
          if (response.ok) {
            return cache.put(resource, response);
          }
        } catch (error) {
          log(`Failed to preload: ${resource}`, error);
        }
      })
    );
  },

  // Error response generator
  createErrorResponse(message, status = 503) {
    return new Response(
      `<html>
        <head>
          <title>Error - ${status}</title>
          <style>
            body { font-family: system-ui; padding: 2rem; text-align: center; }
            .error { color: #EF4444; }
          </style>
        </head>
        <body>
          <h1 class="error">Error ${status}</h1>
          <p>${message}</p>
          <button onclick="window.location.reload()">Retry</button>
        </body>
      </html>`,
      {
        status: status,
        headers: { 'Content-Type': 'text/html' }
      }
    );
  }
};

// Request timeout wrapper
const timeoutPromise = (promise, timeout) => {
  return Promise.race([
    promise,
    new Promise((_, reject) => 
      setTimeout(() => reject(new Error('Request timeout')), timeout)
    )
  ]);
};

// Advanced caching strategies
const strategies = {
  // Cache first with network fallback and periodic update
  async cacheFirstUpdate(request, cacheName = CONFIG.cacheNames.static) {
    const cache = await caches.open(cacheName);
    const cachedResponse = await cache.match(request);
    
    // Return cached response immediately
    if (cachedResponse) {
      // Update cache in background
      this.updateCache(request, cache).catch(log);
      return cachedResponse;
    }
    
    try {
      const networkResponse = await fetch(request);
      await cache.put(request, networkResponse.clone());
      return networkResponse;
    } catch (error) {
      return utils.createErrorResponse(
        'Failed to fetch resource. Please try again later.'
      );
    }
  },

  // Network first with timeout and cache fallback
  async networkFirstTimeout(request, timeout, cacheName = CONFIG.cacheNames.dynamic) {
    try {
      const networkResponse = await timeoutPromise(fetch(request), timeout);
      if (networkResponse.ok) {
        const cache = await caches.open(cacheName);
        await cache.put(request, networkResponse.clone());
        return networkResponse;
      }
    } catch (error) {
      log('Network request failed:', error);
    }
    
    const cache = await caches.open(cacheName);
    const cachedResponse = await cache.match(request);
    
    if (cachedResponse) {
      return cachedResponse;
    }
    
    return utils.createErrorResponse(
      'Unable to fetch resource. Please check your connection.'
    );
  },

  // Stale while revalidate with error recovery
  async staleWhileRevalidate(request, cacheName = CONFIG.cacheNames.dynamic) {
    const cache = await caches.open(cacheName);
    const cachedResponse = await cache.match(request);
    
    const networkPromise = utils.retry(async () => {
      const response = await fetch(request);
      if (response.ok) {
        await cache.put(request, response.clone());
      }
      return response;
    }).catch(error => {
      log('Network revalidation failed:', error);
      return null;
    });
    
    return cachedResponse || networkPromise || utils.createErrorResponse(
      'Resource temporarily unavailable.'
    );
  }
};

// Cache update helper
async function updateCache(request, cache) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      await cache.put(request, response);
    }
  } catch (error) {
    log('Background cache update failed:', error);
  }
}