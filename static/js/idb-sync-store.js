/**
 * AbhiHub IndexedDB Client Store & Delta Sync Engine
 * Manages client-side IndexedDB caching for:
 * - Colleges list (`colleges` - common across all users)
 * - Subjects list (`subjects` - common across all users)
 * - Recently accessed files (`files` - user specific)
 * - User profile metadata (`user_meta` - user specific)
 * - Sync metadata & version tags (`sync_meta`)
 */
(function(window) {
  'use strict';

  const DB_NAME = 'AbhiHubDataStore';
  const DB_VERSION = 2;
  const STORES = {
    FILES: 'files',
    COLLEGES: 'colleges',
    DEPARTMENTS: 'departments',
    SUBJECTS: 'subjects',
    USER_META: 'user_meta',
    SYNC_META: 'sync_meta'
  };

  let dbPromise = null;

  function openDB() {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise((resolve, reject) => {
      if (!window.indexedDB) {
        return reject(new Error('IndexedDB not supported'));
      }
      const req = window.indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(STORES.FILES)) {
          const s = db.createObjectStore(STORES.FILES, { keyPath: 'id' });
          try { s.createIndex('accessed_at', 'accessed_at', { unique: false }); } catch (_) {}
        }
        if (!db.objectStoreNames.contains(STORES.COLLEGES)) {
          db.createObjectStore(STORES.COLLEGES, { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains(STORES.DEPARTMENTS)) {
          db.createObjectStore(STORES.DEPARTMENTS, { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains(STORES.SUBJECTS)) {
          db.createObjectStore(STORES.SUBJECTS, { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains(STORES.USER_META)) {
          db.createObjectStore(STORES.USER_META, { keyPath: 'key' });
        }
        if (!db.objectStoreNames.contains(STORES.SYNC_META)) {
          db.createObjectStore(STORES.SYNC_META, { keyPath: 'store' });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return dbPromise;
  }

  const AbhiHubIDB = {
    STORES,

    async get(storeName, key) {
      const db = await openDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readonly');
        const req = tx.objectStore(storeName).get(key);
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => reject(req.error);
      });
    },

    async getAll(storeName) {
      const db = await openDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readonly');
        const req = tx.objectStore(storeName).getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = () => reject(req.error);
      });
    },

    async put(storeName, item) {
      const db = await openDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readwrite');
        const req = tx.objectStore(storeName).put(item);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
    },

    async putMany(storeName, items, clearFirst = false) {
      const db = await openDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readwrite');
        const store = tx.objectStore(storeName);
        if (clearFirst) store.clear();
        for (const item of (items || [])) {
          if (!item || typeof item !== 'object') continue;
          if (store.keyPath && !item[store.keyPath]) {
            if (store.keyPath === 'id') {
              item.id = item.document_id || item.doc_id || item.file_id || item.key || item._id;
            } else if (store.keyPath === 'key') {
              item.key = item.id || item.store || item.name || 'default';
            }
          }
          if (store.keyPath && !item[store.keyPath]) continue;
          try {
            store.put(item);
          } catch (_) {}
        }
        tx.oncomplete = () => resolve(true);
        tx.onerror = () => reject(tx.error);
      });
    },

    async clear(storeName) {
      const db = await openDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readwrite');
        const req = tx.objectStore(storeName).clear();
        req.onsuccess = () => resolve(true);
        req.onerror = () => reject(req.error);
      });
    },

    async getSyncMeta(storeName) {
      try {
        return await this.get(STORES.SYNC_META, storeName);
      } catch (_) {
        return null;
      }
    },

    async setSyncMeta(storeName, version) {
      try {
        return await this.put(STORES.SYNC_META, {
          store: storeName,
          version: version || 'synced',
          last_synced: Date.now()
        });
      } catch (_) {
        return null;
      }
    },

    // Cache-First Fast Getters
    async getColleges() {
      try {
        const cached = await this.getAll(STORES.COLLEGES);
        if (cached && cached.length > 0) return cached;
      } catch (_) {}
      try {
        const res = await fetch('/api/colleges');
        const data = await res.json();
        const list = data.colleges || data.data || [];
        if (list.length > 0) await this.putMany(STORES.COLLEGES, list, true);
        return list;
      } catch (_) {
        return [];
      }
    },

    async getDepartments(collegeId) {
      try {
        const cached = await this.getAll(STORES.DEPARTMENTS);
        if (cached && cached.length > 0) {
          if (!collegeId) return cached;
          return cached.filter(d => String(d.college_id) === String(collegeId));
        }
      } catch (_) {}
      try {
        const url = collegeId ? `/api/departments?college_id=${encodeURIComponent(collegeId)}` : '/api/departments';
        const res = await fetch(url);
        const data = await res.json();
        const list = data.departments || data.data || [];
        if (!collegeId && list.length > 0) await this.putMany(STORES.DEPARTMENTS, list, true);
        return list;
      } catch (_) {
        return [];
      }
    },

    async getUserDetails() {
      return await this.getUserMeta();
    },

    async getSubjects(departmentId) {
      try {
        const cached = await this.getAll(STORES.SUBJECTS);
        if (cached && cached.length > 0) {
          if (!departmentId) return cached;
          return cached.filter(s => String(s.department_id) === String(departmentId));
        }
      } catch (_) {}
      try {
        const url = departmentId ? `/api/subjects?department_id=${encodeURIComponent(departmentId)}` : '/api/subjects';
        const res = await fetch(url);
        const data = await res.json();
        const list = data.subjects || data.data || [];
        if (!departmentId && list.length > 0) await this.putMany(STORES.SUBJECTS, list, true);
        return list;
      } catch (_) {
        return [];
      }
    },

    async getRecentFiles() {
      try {
        return await this.getAll(STORES.FILES);
      } catch (_) {
        return [];
      }
    },

    async getUserMeta() {
      try {
        return await this.get(STORES.USER_META, 'current_user');
      } catch (_) {
        return null;
      }
    },

    async syncStore(storeName, endpoint, newVersion) {
      try {
        const res = await fetch(endpoint, { headers: { 'Accept': 'application/json' } });
        if (!res.ok) return false;
        const data = await res.json();
        if (!data || !data.success) return false;

        if (storeName === STORES.COLLEGES) {
          const list = data.colleges || data.data || [];
          await this.putMany(STORES.COLLEGES, list, true);
        } else if (storeName === STORES.DEPARTMENTS) {
          const list = data.departments || data.data || [];
          await this.putMany(STORES.DEPARTMENTS, list, true);
        } else if (storeName === STORES.SUBJECTS) {
          const list = data.subjects || data.data || [];
          await this.putMany(STORES.SUBJECTS, list, true);
        } else if (storeName === STORES.FILES) {
          const list = data.data || data.files || [];
          await this.putMany(STORES.FILES, list, true);
        } else if (storeName === STORES.USER_META) {
          const user = data.user || data;
          await this.put(STORES.USER_META, { key: 'current_user', ...user });
        }

        await this.setSyncMeta(storeName, newVersion);
        window.dispatchEvent(new CustomEvent('abhihub:idb_synced', {
          detail: { store: storeName, version: newVersion }
        }));
        return true;
      } catch (err) {
        console.warn(`[AbhiHubIDB] Sync failed for ${storeName}:`, err);
        return false;
      }
    },

    _lastSyncTime: 0,
    async syncAll(force = false) {
      const now = Date.now();
      if (!force && now - this._lastSyncTime < 60000) return;
      this._lastSyncTime = now;
      try {
        const res = await fetch('/api/sync/versions', { headers: { 'Accept': 'application/json' } });
        if (!res.ok) return;
        const body = await res.json();
        if (!body || !body.success) return;

        // Account-Switch Isolation:
        // Common info (colleges, subjects) is preserved for any user.
        // If a different user logged in, flush only user-specific stores.
        const currentUserId = body.user_id || 'guest';
        const sessionMeta = await this.getSyncMeta('session_user');
        if (sessionMeta && sessionMeta.version !== currentUserId) {
          await this.clear(STORES.FILES);
          await this.clear(STORES.USER_META);
        }
        await this.setSyncMeta('session_user', currentUserId);

        const { versions, endpoints } = body;
        const storeMap = {
          colleges: STORES.COLLEGES,
          departments: STORES.DEPARTMENTS,
          subjects: STORES.SUBJECTS,
          recent_files: STORES.FILES,
          user_meta: STORES.USER_META
        };

        const syncTasks = [];
        for (const [key, serverVer] of Object.entries(versions || {})) {
          if (!serverVer) continue;
          const storeName = storeMap[key];
          if (!storeName || !endpoints[key]) continue;

          syncTasks.push((async () => {
            const localMeta = await this.getSyncMeta(storeName);
            const isOutdated = force || !localMeta || localMeta.version !== serverVer;
            if (isOutdated) {
              await this.syncStore(storeName, endpoints[key], serverVer);
            }
          })());
        }
        await Promise.allSettled(syncTasks);
      } catch (e) {
        console.warn('[AbhiHubIDB] Check versions error:', e);
      }
    },

    initPeriodicSync(intervalMs = 300000) {
      setTimeout(() => this.syncAll(), 1200);

      document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
          this.syncAll();
        }
      });

      setInterval(() => {
        if (!document.hidden) {
          this.syncAll();
        }
      }, intervalMs);
    }
  };

  window.AbhiHubIDB = AbhiHubIDB;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => AbhiHubIDB.initPeriodicSync());
  } else {
    AbhiHubIDB.initPeriodicSync();
  }
})(window);
