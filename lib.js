// Pure logic of the player (no DOM, no storage) — unit-tested with node --test.

export const AUDIO_EXT = ['mp3', 'm4a', 'aac', 'wav', 'flac', 'ogg', 'opus'];
export const FORMAT_VERSION = 1;

export function stem(name) {
  const i = name.lastIndexOf('.');
  return i > 0 ? name.slice(0, i) : name;
}

export function ext(name) {
  const i = name.lastIndexOf('.');
  return i > 0 ? name.slice(i + 1).toLowerCase() : '';
}

export function fmtTime(t) {
  t = Math.max(0, Math.floor(t || 0));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  const ss = String(s).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

export function words(text) {
  return text.match(/\S+/g) || [];
}

// Validates a generator X.json; throws Error with a human-readable message.
export function validateEpisode(data) {
  const fail = (msg) => { throw new Error(msg); };
  if (!data || typeof data !== 'object') fail('not a JSON object');
  if (data.version !== FORMAT_VERSION) fail(`unknown format version: ${data.version}`);
  if (!Array.isArray(data.cues) || !data.cues.length) fail('no cues');
  if (!Array.isArray(data.sentences)) fail('no sentences');
  if (typeof data.audio !== 'string' || !data.audio) fail('no audio file name');
  data.cues.forEach((c, i) => {
    if (typeof c.s !== 'number' || typeof c.e !== 'number' || typeof c.t !== 'string') fail(`cue ${i} is broken`);
  });
  data.sentences.forEach((s, i) => {
    const ok = Array.isArray(s.from) && Array.isArray(s.to) && typeof s.t === 'string' && typeof s.tr === 'string'
      && s.from[0] >= 0 && s.to[0] < data.cues.length;
    if (!ok) fail(`sentence ${i} is broken`);
  });
  return data;
}

// Groups picked files into episodes. `files` items need {name}, and
// {webkitRelativePath} when a folder was picked (pairs only within one folder).
// JSON content is read by the caller; jsonAudioName(json) is its "audio" field.
// A leftover audio next to a paired episode with the same name (X.mp3 when
// X.json points to the generator's X.m4a) is skipped silently. In a folder,
// files that are neither audio nor JSON (subtitles etc.) are skipped silently too.
// Returns {pairs: [{json, audio}], errors: [string], orphans: [audio without JSON]}.
export function pairFiles(files, jsonAudioName, { folder = false } = {}) {
  const dir = (f) => { const p = f.webkitRelativePath || ''; return p.slice(0, p.lastIndexOf('/') + 1); };
  const key = (f, name = f.name) => dir(f) + stem(name);
  const jsons = files.filter((f) => ext(f.name) === 'json');
  const audios = files.filter((f) => AUDIO_EXT.includes(ext(f.name)));
  const pairs = [], errors = [], orphans = [], used = new Set(), done = new Set();
  for (const j of jsons) {
    const wanted = jsonAudioName(j);
    const near = audios.filter((a) => !used.has(a) && dir(a) === dir(j));
    const audio = near.find((a) => a.name === wanted)
      || near.find((a) => stem(a.name) === stem(j.name) && (!wanted || ext(a.name) === ext(wanted)));
    if (audio) {
      pairs.push({ json: j, audio });
      used.add(audio);
      done.add(key(j)).add(key(audio));
      continue;
    }
    const other = near.find((a) => stem(a.name) === stem(j.name));
    if (other) {
      used.add(other);
      errors.push(`${j.name}: needs ${wanted}, not ${other.name}`);
    } else errors.push(`${j.name}: audio file not selected: ${wanted || stem(j.name) + '.mp3'}`);
    done.add(key(j));
  }
  for (const a of audios) {
    if (used.has(a) || done.has(key(a))) continue;
    orphans.push(a);
    errors.push(`${a.name}: missing ${stem(a.name)}.json`);
  }
  if (!folder) {
    for (const f of files) {
      if (!jsons.includes(f) && !audios.includes(f)) errors.push(`${f.name}: not audio or .json — skipped`);
    }
  }
  return { pairs, errors, orphans };
}

// Index of the last cue whose start <= t (-1 before the first cue).
export function cueAt(cues, t) {
  let lo = 0, hi = cues.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (cues[mid].s <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

// For every cue, an array mapping word index -> sentence index.
export function buildWordToSentence(cues, sentences) {
  const map = cues.map((c) => new Array(words(c.t).length).fill(-1));
  sentences.forEach((s, si) => {
    const [c0, w0] = s.from, [c1, w1] = s.to;
    for (let ci = c0; ci <= c1; ci++) {
      const row = map[ci];
      if (!row) continue;
      const lo = ci === c0 ? w0 : 0, hi = ci === c1 ? w1 : row.length - 1;
      for (let wi = lo; wi <= hi && wi < row.length; wi++) row[wi] = si;
    }
  });
  return map;
}

// Position of a cue word inside its sentence's word list.
export function wordIndexInSentence(cues, sentence, ci, wi) {
  const [c0, w0] = sentence.from;
  if (ci === c0) return wi - w0;
  let n = words(cues[c0].t).length - w0;
  for (let k = c0 + 1; k < ci; k++) n += words(cues[k].t).length;
  return n + wi;
}

// Cues where each sentence ends -> list of sentence indices (for inline translations).
export function sentencesEndingAt(cues, sentences) {
  const out = cues.map(() => []);
  sentences.forEach((s, si) => { if (out[s.to[0]]) out[s.to[0]].push(si); });
  return out;
}

export function episodeId(data) {
  return stem(data.audio);
}

// Playlist order: by title, numbers compared as numbers (Episode 2 < Episode 10).
export function sortEpisodes(eps) {
  return [...eps].sort((a, b) => a.title.localeCompare(b.title, undefined, { numeric: true }));
}

// The id d steps away from id in the ordered list of ids, or null.
export function neighbor(ids, id, d) {
  const i = ids.indexOf(id);
  return i < 0 ? null : ids[i + d] ?? null;
}

// Played to the end (the player then starts it over).
export function isFinished(pos, dur) {
  return dur > 0 && pos >= dur - 2;
}

export function duration(data) {
  return data.cues.length ? data.cues[data.cues.length - 1].e : 0;
}

export const RATES = [0.75, 0.85, 1, 1.15, 1.25, 1.5];

export function nextRate(r) {
  const i = RATES.indexOf(r);
  return RATES[(i + 1) % RATES.length];
}

export function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}
