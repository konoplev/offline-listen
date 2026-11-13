// IndexedDB storage: episodes (metadata + JSON data) and audio blobs.
// Audio lives in its own store so the library list doesn't load megabytes.

const DB_NAME = 'offline-listen';
const DB_VERSION = 1;
let dbPromise = null;

function open() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        db.createObjectStore('episodes', { keyPath: 'id' });
        db.createObjectStore('audio');
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  return dbPromise;
}

function tx(stores, mode, fn) {
  return open().then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(stores, mode);
    let result;
    Promise.resolve(fn(t)).then((r) => { result = r; });
    t.oncomplete = () => resolve(result);
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error || new Error('transaction aborted'));
  }));
}

function req(r) {
  return new Promise((resolve, reject) => {
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

export function listEpisodes() {
  return tx(['episodes'], 'readonly', (t) => req(t.objectStore('episodes').getAll()));
}

export function getEpisode(id) {
  return tx(['episodes'], 'readonly', (t) => req(t.objectStore('episodes').get(id)));
}

export function getAudio(id) {
  return tx(['audio'], 'readonly', (t) => req(t.objectStore('audio').get(id)));
}

// Saves (or replaces) an episode with its audio.
export async function putEpisode(episode, audioBlob) {
  const ep = { added: Date.now(), ...episode };
  await tx(['episodes', 'audio'], 'readwrite', (t) => {
    t.objectStore('episodes').put(ep);
    t.objectStore('audio').put(audioBlob, ep.id);
  });
  return ep;
}

export function deleteEpisode(id) {
  return tx(['episodes', 'audio'], 'readwrite', (t) => {
    t.objectStore('episodes').delete(id);
    t.objectStore('audio').delete(id);
  });
}
