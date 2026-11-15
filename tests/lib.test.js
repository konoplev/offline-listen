import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  stem, ext, fmtTime, words, validateEpisode, pairFiles, cueAt, buildWordToSentence,
  wordIndexInSentence, sentencesEndingAt, episodeId, duration, nextRate, RATES, clamp,
  sortEpisodes, neighbor, isFinished,
} from '../lib.js';

const cues = [
  { s: 0, e: 3, t: 'Welcome back. Today we' },  // 0..4
  { s: 3, e: 6, t: 'talk with Dr. Smith' },      // 0..3
  { s: 6, e: 9, t: 'about Kubernetes. Bye!' },    // 0..2
];
const sentences = [
  { s: 0, e: 1.2, from: [0, 0], to: [0, 1], t: 'Welcome back.', tr: 'С возвращением.' },
  { s: 1.2, e: 8, from: [0, 2], to: [2, 1], t: 'Today we talk with Dr. Smith about Kubernetes.', tr: 'Сегодня…' },
  { s: 8, e: 9, from: [2, 2], to: [2, 2], t: 'Bye!', tr: 'Пока!' },
];
const episode = () => ({ version: 1, title: 'Ep 1', audio: 'Ep 1.mp3', src: 'en', tgt: 'ru', cues, sentences });

test('stem / ext', () => {
  assert.equal(stem('Episode 1.mp3'), 'Episode 1');
  assert.equal(stem('a.b.json'), 'a.b');
  assert.equal(stem('.hidden'), '.hidden');
  assert.equal(ext('X.MP3'), 'mp3');
  assert.equal(ext('noext'), '');
});

test('fmtTime', () => {
  assert.equal(fmtTime(0), '0:00');
  assert.equal(fmtTime(65.9), '1:05');
  assert.equal(fmtTime(3725), '1:02:05');
  assert.equal(fmtTime(-3), '0:00');
  assert.equal(fmtTime(undefined), '0:00');
});

test('words splits like the generator (whitespace)', () => {
  assert.deepEqual(words('  a  b,\tc. '), ['a', 'b,', 'c.']);
  assert.deepEqual(words(''), []);
});

test('validateEpisode accepts generator output', () => {
  assert.equal(validateEpisode(episode()).title, 'Ep 1');
});

test('validateEpisode rejects broken data with readable messages', () => {
  assert.throws(() => validateEpisode(null), /not a JSON/);
  assert.throws(() => validateEpisode({ ...episode(), version: 2 }), /format version/);
  assert.throws(() => validateEpisode({ ...episode(), cues: [] }), /no cues/);
  assert.throws(() => validateEpisode({ ...episode(), sentences: undefined }), /no sentences/);
  assert.throws(() => validateEpisode({ ...episode(), audio: '' }), /audio file/);
  assert.throws(() => validateEpisode({ ...episode(), cues: [{ s: 0, t: 'x' }] }), /cue 0/);
  assert.throws(() => validateEpisode({ ...episode(), sentences: [{ ...sentences[0], to: [9, 0] }] }), /sentence 0/);
});

test('pairFiles pairs by the audio name in json, then by stem', () => {
  const f = (name) => ({ name });
  const files = [f('A.json'), f('A.mp3'), f('B.json'), f('B.m4a'), f('C.json'), f('D.mp3'), f('notes.txt')];
  const audioOf = { 'A.json': 'A.mp3', 'B.json': 'renamed.m4a', 'C.json': 'C.mp3' };
  const { pairs, errors } = pairFiles(files, (j) => audioOf[j.name]);
  assert.deepEqual(pairs.map((p) => [p.json.name, p.audio.name]), [['A.json', 'A.mp3'], ['B.json', 'B.m4a']]);
  assert.deepEqual(errors, [
    'C.json: audio file not selected: C.mp3',
    'D.mp3: missing D.json',
    'notes.txt: not audio or .json — skipped',
  ]);
});

test('pairFiles: orphans are audio files without a JSON', () => {
  const f = (name) => ({ name });
  const { orphans } = pairFiles([f('A.json'), f('A.mp3'), f('D.mp3')], () => 'A.mp3');
  assert.deepEqual(orphans.map((a) => a.name), ['D.mp3']);
});

test('pairFiles: folder from the generator (X.mp3 + X.m4a + X.json + srt)', () => {
  const f = (name, dir = 'pods/') => ({ name, webkitRelativePath: dir + name });
  const files = [f('X.mp3'), f('X.m4a'), f('X.json'), f('X.srt'), f('X.ru.srt'), f('Y.mp3'), f('Y.json'), f('Z.mp3'),
    f('.DS_Store')];
  const audioOf = { 'X.json': 'X.m4a', 'Y.json': 'Y.mp3' };
  const { pairs, errors, orphans } = pairFiles(files, (j) => audioOf[j.name], { folder: true });
  assert.deepEqual(pairs.map((p) => [p.json.name, p.audio.name]), [['X.json', 'X.m4a'], ['Y.json', 'Y.mp3']]);
  assert.deepEqual(errors, ['Z.mp3: missing Z.json']);  // the source X.mp3 and subtitles are skipped silently
  assert.deepEqual(orphans.map((a) => a.name), ['Z.mp3']);
});

test('pairFiles: in a folder, files pair only within their subfolder', () => {
  const f = (path) => ({ name: path.split('/').pop(), webkitRelativePath: path });
  const files = [f('r/a/E.json'), f('r/b/E.mp3'), f('r/b/E.json'), f('r/a/E.mp3')];
  const { pairs, errors } = pairFiles(files, () => 'E.mp3', { folder: true });
  assert.deepEqual(pairs.map((p) => [p.json.webkitRelativePath, p.audio.webkitRelativePath]),
    [['r/a/E.json', 'r/a/E.mp3'], ['r/b/E.json', 'r/b/E.mp3']]);
  assert.deepEqual(errors, []);
});

test('pairFiles: JSON made for X.m4a does not take the VBR X.mp3', () => {
  const f = (name) => ({ name });
  const { pairs, errors, orphans } = pairFiles([f('X.json'), f('X.mp3')], () => 'X.m4a');
  assert.deepEqual(pairs, []);
  assert.deepEqual(errors, ['X.json: needs X.m4a, not X.mp3']);
  assert.deepEqual(orphans, []);
});

test('sortEpisodes: numbers in titles compare as numbers', () => {
  const eps = ['Episode 10', 'Episode 2', 'Bonus', 'Episode 1'].map((title) => ({ title }));
  assert.deepEqual(sortEpisodes(eps).map((e) => e.title), ['Bonus', 'Episode 1', 'Episode 2', 'Episode 10']);
  assert.equal(eps[0].title, 'Episode 10');  // not sorted in place
});

test('neighbor / isFinished', () => {
  assert.equal(neighbor(['a', 'b', 'c'], 'b', 1), 'c');
  assert.equal(neighbor(['a', 'b', 'c'], 'b', -1), 'a');
  assert.equal(neighbor(['a', 'b', 'c'], 'c', 1), null);
  assert.equal(neighbor(['a', 'b', 'c'], 'a', -1), null);
  assert.equal(neighbor(['a'], 'x', 1), null);
  assert.equal(isFinished(98.5, 100), true);
  assert.equal(isFinished(90, 100), false);
  assert.equal(isFinished(0, 0), false);
});

test('cueAt: last cue starting at or before t', () => {
  assert.equal(cueAt(cues, -1), -1);
  assert.equal(cueAt(cues, 0), 0);
  assert.equal(cueAt(cues, 2.99), 0);
  assert.equal(cueAt(cues, 3), 1);
  assert.equal(cueAt(cues, 100), 2);
  assert.equal(cueAt([], 1), -1);
});

test('buildWordToSentence maps every word, across cue boundaries', () => {
  assert.deepEqual(buildWordToSentence(cues, sentences), [
    [0, 0, 1, 1],      // Welcome back. | Today we
    [1, 1, 1, 1],      // talk with Dr. Smith
    [1, 1, 2],         // about Kubernetes. | Bye!
  ]);
});

test('buildWordToSentence tolerates out-of-range positions', () => {
  const map = buildWordToSentence(cues, [{ from: [2, 1], to: [5, 9], t: '', tr: '' }]);
  assert.deepEqual(map[2], [-1, 0, 0]);
});

test('wordIndexInSentence', () => {
  assert.equal(wordIndexInSentence(cues, sentences[1], 0, 2), 0);  // Today
  assert.equal(wordIndexInSentence(cues, sentences[1], 0, 3), 1);  // we
  assert.equal(wordIndexInSentence(cues, sentences[1], 1, 3), 5);  // Smith
  assert.equal(wordIndexInSentence(cues, sentences[1], 2, 1), 7);  // Kubernetes.
  assert.equal(words(sentences[1].t)[7], 'Kubernetes.');
});

test('sentencesEndingAt groups sentences by their last cue', () => {
  assert.deepEqual(sentencesEndingAt(cues, sentences), [[0], [], [1, 2]]);
});

test('episodeId / duration', () => {
  assert.equal(episodeId(episode()), 'Ep 1');
  assert.equal(duration(episode()), 9);
  assert.equal(duration({ cues: [] }), 0);
});

test('nextRate cycles and recovers from unknown values', () => {
  assert.equal(nextRate(1), 1.15);
  assert.equal(nextRate(RATES[RATES.length - 1]), RATES[0]);
  assert.equal(nextRate(2), RATES[0]);
});

test('clamp', () => {
  assert.equal(clamp(5, 0, 3), 3);
  assert.equal(clamp(-1, 0, 3), 0);
  assert.equal(clamp(2, 0, 3), 2);
});
