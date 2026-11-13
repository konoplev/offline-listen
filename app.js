import * as db from './db.js';
import {
  validateEpisode, pairFiles, cueAt, buildWordToSentence, wordIndexInSentence, sentencesEndingAt,
  episodeId, duration, fmtTime, words, nextRate, clamp,
} from './lib.js';

const $ = (id) => document.getElementById(id);
const audio = $('audio');
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// Small per-device settings live in localStorage: writes are synchronous, so
// nothing is lost when iOS kills the app right after a pause (an IndexedDB
// write may not have committed yet).
const prefs = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* private mode */ } },
  pos(id) { return parseFloat(this.get(`pos:${id}`)) || 0; },
  setPos(id, t) { this.set(`pos:${id}`, String(Math.round(t * 10) / 10)); },
  rate() { return parseFloat(this.get('rate')) || 1; },
};

// ---------------------------------------------------------------- routing
function route() {
  const m = location.hash.match(/^#\/ep\/(.+)$/);
  if (m) openEpisode(decodeURIComponent(m[1]));
  else showLibrary();
}
window.addEventListener('hashchange', route);

// ---------------------------------------------------------------- library
async function showLibrary() {
  closeEpisode();
  $('player').hidden = true;
  $('library').hidden = false;
  document.title = 'Listen';
  const eps = (await db.listEpisodes()).sort((a, b) => a.title.localeCompare(b.title, undefined, { numeric: true }));
  $('empty').hidden = eps.length > 0;
  $('episodes').innerHTML = eps.map((ep) => {
    const dur = duration(ep.data), pos = prefs.pos(ep.id), pct = dur ? Math.min(100, (pos / dur) * 100) : 0;
    return `<li class="ep" data-id="${esc(ep.id)}">
      <button class="ep-open">
        <div class="ep-title">${esc(ep.title)}</div>
        <div class="ep-meta">${fmtTime(pos)} / ${fmtTime(dur)} · ${ep.data.cues.length} lines</div>
        <div class="progress"><div style="width:${pct.toFixed(1)}%"></div></div>
      </button>
      <button class="ep-del">Delete</button>
    </li>`;
  }).join('');
  showStorage();
}

async function showStorage() {
  try {
    const { usage } = await navigator.storage.estimate();
    $('storage').textContent = usage ? `Used on device: ${(usage / 1048576).toFixed(1)} MB` : '';
  } catch { $('storage').textContent = ''; }
}

$('episodes').addEventListener('click', async (e) => {
  const li = e.target.closest('.ep');
  if (!li) return;
  const id = li.dataset.id;
  const del = e.target.closest('.ep-del');
  if (del) {
    // two-step delete instead of confirm() (dialogs are unreliable in home-screen apps)
    if (!del.classList.contains('confirm')) {
      del.classList.add('confirm');
      del.textContent = 'Sure?';
      setTimeout(() => { if (del.isConnected) { del.classList.remove('confirm'); del.textContent = 'Delete'; } }, 3000);
      return;
    }
    await db.deleteEpisode(id);
    prefs.del(`pos:${id}`);
    showLibrary();
    return;
  }
  if (e.target.closest('.ep-open')) location.hash = `#/ep/${encodeURIComponent(id)}`;
});

$('import').addEventListener('change', async (e) => {
  const files = [...e.target.files];
  e.target.value = '';
  if (!files.length) return;
  const msg = [];
  const parsed = new Map();
  for (const f of files.filter((f) => f.name.toLowerCase().endsWith('.json'))) {
    try { parsed.set(f, validateEpisode(JSON.parse(await f.text()))); }
    catch (err) { msg.push(`${f.name}: ${err.message}`); }
  }
  const valid = files.filter((f) => !f.name.toLowerCase().endsWith('.json') || parsed.has(f));
  const { pairs, errors } = pairFiles(valid, (j) => parsed.get(j).audio);
  msg.push(...errors);
  let added = 0;
  for (const { json, audio: audioFile } of pairs) {
    const data = parsed.get(json);
    try {
      await db.putEpisode({ id: episodeId(data), title: data.title || episodeId(data), data, size: audioFile.size }, audioFile);
      added++;
    } catch (err) {
      msg.push(`${json.name}: could not save (${err.message || err})`);
    }
  }
  if (added) msg.unshift(`Episodes added: ${added}`);
  $('import-msg').textContent = msg.join('\n');
  $('import-msg').hidden = !msg.length;
  $('import-msg').classList.toggle('error', !added);
  try { await navigator.storage?.persist?.(); } catch { /* best effort */ }
  showLibrary();
});

// ---------------------------------------------------------------- player
let cur = null; // { ep, data, w2s, rows, current, objectUrl }
let saveTimer = 0;

async function openEpisode(id) {
  if (cur && cur.ep.id === id) return;
  closeEpisode();
  const ep = await db.getEpisode(id);
  const blob = ep && await db.getAudio(id);
  if (!ep || !blob) { location.hash = ''; return; }

  const data = ep.data;
  cur = {
    ep, data,
    w2s: buildWordToSentence(data.cues, data.sentences),
    current: -1,
    objectUrl: URL.createObjectURL(blob),
    restored: false,
  };
  $('library').hidden = true;
  $('player').hidden = false;
  $('player-msg').hidden = true;
  $('ep-title').textContent = ep.title;
  document.title = ep.title;
  renderCues(data);
  setRate(prefs.rate());
  $('seek').max = duration(data) || 1;
  $('dur').textContent = fmtTime(duration(data));
  updateTime(prefs.pos(id));
  audio.src = cur.objectUrl;
  audio.load();
  window.scrollTo(0, 0);
  setupMediaSession(ep.title);
}

function closeEpisode() {
  if (!cur) return;
  savePosition();
  audio.pause();
  closeSheet(false);
  audio.removeAttribute('src');
  audio.load();
  URL.revokeObjectURL(cur.objectUrl);
  cur = null;
  $('cues').innerHTML = '';
}

function renderCues(data) {
  const endsAt = sentencesEndingAt(data.cues, data.sentences);
  const html = [];
  data.cues.forEach((c, i) => {
    html.push(`<div class="cue" data-i="${i}"><span class="ts" data-seek="${i}">${fmtTime(c.s)}</span>`);
    words(c.t).forEach((w, k) => html.push(`<span class="w" data-w="${k}">${esc(w)}</span> `));
    html.push('</div>');
    for (const si of endsAt[i]) html.push(`<div class="tr">${esc(data.sentences[si].tr)}</div>`);
  });
  $('cues').innerHTML = html.join('');
  cur.rows = $('cues').querySelectorAll('.cue');
}

function play() { const p = audio.play(); if (p) p.catch(() => {}); }
function toggle() { if (audio.paused) play(); else audio.pause(); }
function seekTo(t) {
  audio.currentTime = clamp(t, 0, audio.duration || duration(cur.data));
  updateTime(audio.currentTime);
}
function skip(d) { seekTo(audio.currentTime + d); }

$('play').onclick = toggle;
document.querySelectorAll('[data-skip]').forEach((b) => { b.onclick = () => skip(+b.dataset.skip); });
$('back').onclick = () => { location.hash = ''; };

audio.addEventListener('loadedmetadata', () => {
  if (!cur) return;
  $('seek').max = audio.duration || duration(cur.data);
  $('dur').textContent = fmtTime(audio.duration);
  if (!cur.restored) {
    cur.restored = true;
    const pos = prefs.pos(cur.ep.id);
    if (pos > 0 && pos < audio.duration - 2) audio.currentTime = pos;  // finished episodes start over
    updateTime(audio.currentTime);
  }
  audio.playbackRate = prefs.rate();
});
audio.addEventListener('error', () => {
  if (!cur || !audio.getAttribute('src')) return;
  $('player-msg').textContent = 'Cannot play the audio. Try deleting the episode and adding it again.';
  $('player-msg').hidden = false;
});
audio.addEventListener('play', () => { $('play').textContent = '❚❚'; $('play').setAttribute('aria-label', 'Pause'); });
audio.addEventListener('pause', () => {
  $('play').textContent = '▶';
  $('play').setAttribute('aria-label', 'Play');
  savePosition();
});
document.addEventListener('visibilitychange', () => { if (document.hidden) savePosition(); });
window.addEventListener('pagehide', savePosition);

function savePosition() {
  if (!cur || !audio.getAttribute('src')) return;
  const pos = audio.currentTime;
  if (pos >= 0) prefs.setPos(cur.ep.id, pos);
}

// speed
function setRate(r) {
  audio.playbackRate = r;
  audio.defaultPlaybackRate = r;
  $('speed').textContent = `${r}×`;
  prefs.set('rate', String(r));
}
$('speed').onclick = () => setRate(nextRate(audio.playbackRate));

// inline translations
function setShowTr(on) {
  document.body.classList.toggle('show-tr', on);
  $('tr-toggle').classList.toggle('on', on);
  prefs.set('show-tr', on ? '1' : '0');
}
setShowTr(prefs.get('show-tr') === '1');
$('tr-toggle').onclick = () => setShowTr(!document.body.classList.contains('show-tr'));

// seek slider
let dragging = false;
$('seek').addEventListener('input', () => { dragging = true; $('cur').textContent = fmtTime(+$('seek').value); });
$('seek').addEventListener('change', () => { dragging = false; seekTo(+$('seek').value); });

// ---------------------------------------------------------------- current cue + auto-scroll
let userScrollUntil = 0, autoScrolling = false;
window.addEventListener('scroll', () => { if (!autoScrolling) userScrollUntil = Date.now() + 4000; }, { passive: true });

function scrollToRow(row) {
  autoScrolling = true;
  const r = row.getBoundingClientRect();
  window.scrollTo(0, window.scrollY + r.top - window.innerHeight * 0.35);
  requestAnimationFrame(() => requestAnimationFrame(() => { autoScrolling = false; }));
}

function updateTime(t) {
  if (!cur) return;
  if (!dragging) { $('seek').value = t; $('cur').textContent = fmtTime(t); }
  const i = cueAt(cur.data.cues, t);
  if (i === cur.current) return;
  cur.rows[cur.current]?.classList.remove('active');
  cur.current = i;
  if (i < 0) return;
  cur.rows[i].classList.add('active');
  if (!audio.paused && Date.now() > userScrollUntil) scrollToRow(cur.rows[i]);
}

let lastSave = 0;
audio.addEventListener('timeupdate', () => {
  updateTime(audio.currentTime);
  if (!audio.paused && Date.now() - lastSave > 5000) { lastSave = Date.now(); savePosition(); }
});

// ---------------------------------------------------------------- word tap -> sentence sheet
let sheet = null; // { si, resume, marked: [] }

function sentenceWordEls(s) {
  const els = [];
  for (let ci = s.from[0]; ci <= s.to[0]; ci++) {
    const ws = cur.rows[ci].querySelectorAll('.w');
    const lo = ci === s.from[0] ? s.from[1] : 0, hi = ci === s.to[0] ? s.to[1] : ws.length - 1;
    for (let k = lo; k <= hi; k++) if (ws[k]) els.push(ws[k]);
  }
  return els;
}

function openSheet(wordEl, ci, wi) {
  const resume = sheet ? sheet.resume : !audio.paused;
  closeSheet(false);
  audio.pause();
  const si = cur.w2s[ci]?.[wi] ?? -1;
  const s = cur.data.sentences[si];
  const tapped = words(cur.data.cues[ci].t)[wi];
  const marked = s ? sentenceWordEls(s) : [wordEl];
  marked.forEach((el) => el.classList.add('in-sent'));
  wordEl.classList.add('sel');
  marked.push(wordEl);
  sheet = { si, resume, marked };

  $('s-word').textContent = tapped;
  if (s) {
    const k = wordIndexInSentence(cur.data.cues, s, ci, wi);
    $('s-orig').innerHTML = words(s.t).map((w, j) => (j === k ? `<mark>${esc(w)}</mark>` : esc(w))).join(' ');
    $('s-trans').textContent = s.tr;
  } else {
    $('s-orig').textContent = cur.data.cues[ci].t;
    $('s-trans').textContent = '—';
  }
  $('s-replay').disabled = !s;
  $('sheet-bg').classList.add('open');
  $('sheet').classList.add('open');
  $('sheet').setAttribute('aria-hidden', 'false');
}

function closeSheet(resume) {
  if (!sheet) return;
  sheet.marked.forEach((el) => el.classList.remove('in-sent', 'sel'));
  const shouldResume = resume && sheet.resume;
  sheet = null;
  $('sheet-bg').classList.remove('open');
  $('sheet').classList.remove('open');
  $('sheet').setAttribute('aria-hidden', 'true');
  if (shouldResume) play();
}

$('cues').addEventListener('click', (e) => {
  if (!cur) return;
  const ts = e.target.closest('[data-seek]');
  if (ts) {
    closeSheet(false);
    seekTo(cur.data.cues[+ts.dataset.seek].s);
    userScrollUntil = 0;
    play();
    return;
  }
  const w = e.target.closest('.w');
  if (w) openSheet(w, +w.parentNode.dataset.i, +w.dataset.w);
});
$('sheet-bg').onclick = () => closeSheet(true);
$('s-close').onclick = () => closeSheet(true);
$('s-replay').onclick = () => {
  const s = cur.data.sentences[sheet.si];
  closeSheet(false);
  seekTo(Math.max(0, s.s - 0.15));
  userScrollUntil = 0;
  play();
};

document.addEventListener('keydown', (e) => {
  if (!cur || e.target.tagName === 'INPUT') return;
  if (e.key === ' ') { e.preventDefault(); toggle(); }
  else if (e.key === 'ArrowLeft') skip(-5);
  else if (e.key === 'ArrowRight') skip(5);
  else if (e.key === 'Escape') closeSheet(true);
});

// ---------------------------------------------------------------- lock screen / headphones
function setupMediaSession(title) {
  if (!('mediaSession' in navigator)) return;
  try {
    navigator.mediaSession.metadata = new MediaMetadata({ title, artist: 'Listen' });
    const handlers = {
      play, pause: () => audio.pause(),
      seekbackward: (d) => skip(-(d.seekOffset || 10)),
      seekforward: (d) => skip(d.seekOffset || 10),
      seekto: (d) => seekTo(d.seekTime),
    };
    for (const [k, fn] of Object.entries(handlers)) {
      try { navigator.mediaSession.setActionHandler(k, fn); } catch { /* unsupported action */ }
    }
  } catch { /* old browser */ }
}

// ---------------------------------------------------------------- offline
if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
  navigator.serviceWorker.register('sw.js').catch(() => {});
}

route();
