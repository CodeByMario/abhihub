// File: static/encryptedFileManager.js
// This script manages encrypted files and metadata in IndexedDB for offline access

const DB_NAME = 'EncryptedFilesDB';
const STORE_NAME = 'files';
const META_STORE = 'metadata';
const EXPIRY_DAYS = 2;

function openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = function(event) {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'fileId' });
            }
            if (!db.objectStoreNames.contains(META_STORE)) {
                db.createObjectStore(META_STORE, { keyPath: 'fileId' });
            }
        };
        request.onsuccess = function(event) {
            resolve(event.target.result);
        };
        request.onerror = function(event) {
            reject(event.target.error);
        };
    });
}

async function saveFile(fileId, fileData, metadata) {
    const db = await openDB();
    const tx = db.transaction([STORE_NAME, META_STORE], 'readwrite');
    tx.objectStore(STORE_NAME).put({ fileId, fileData });
    tx.objectStore(META_STORE).put({ ...metadata, fileId, lastAccessed: Date.now() });
    return tx.complete;
}

async function getFile(fileId) {
    const db = await openDB();
    const tx = db.transaction([STORE_NAME, META_STORE], 'readonly');
    const fileReq = tx.objectStore(STORE_NAME).get(fileId);
    const metaReq = tx.objectStore(META_STORE).get(fileId);
    return new Promise((resolve) => {
        fileReq.onsuccess = () => {
            metaReq.onsuccess = () => {
                if (fileReq.result && metaReq.result) {
                    // Update last accessed
                    updateLastAccessed(fileId);
                    resolve({ fileData: fileReq.result.fileData, metadata: metaReq.result });
                } else {
                    resolve(null);
                }
            };
        };
    });
}

async function updateLastAccessed(fileId) {
    const db = await openDB();
    const tx = db.transaction(META_STORE, 'readwrite');
    const req = tx.objectStore(META_STORE).get(fileId);
    req.onsuccess = () => {
        if (req.result) {
            req.result.lastAccessed = Date.now();
            tx.objectStore(META_STORE).put(req.result);
        }
    };
}

async function removeExpiredFiles() {
    const db = await openDB();
    const tx = db.transaction([STORE_NAME, META_STORE], 'readwrite');
    const metaStore = tx.objectStore(META_STORE);
    const now = Date.now();
    metaStore.openCursor().onsuccess = function(event) {
        const cursor = event.target.result;
        if (cursor) {
            const { fileId, lastAccessed } = cursor.value;
            if (now - lastAccessed > EXPIRY_DAYS * 24 * 60 * 60 * 1000) {
                tx.objectStore(STORE_NAME).delete(fileId);
                metaStore.delete(fileId);
            }
            cursor.continue();
        }
    };
}

// Usage example:
// await removeExpiredFiles(); // Call on app start
// let file = await getFile('fileId');
// if (!file) { fetch from server, then saveFile('fileId', fileData, { name, path, ... }) }

window.EncryptedFileManager = { saveFile, getFile, removeExpiredFiles };
