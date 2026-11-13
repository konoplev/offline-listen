# Test scenarios and results

Last checked: 2026-11-13.

How each scenario was checked:
- **Auto (generator):** pytest in `generator/tests/`. The LLM, whisper and the macOS
  translator are replaced with fakes. Slow tests also run the real
  `mlx-community/whisper-large-v3-mlx` from the local cache and the real macOS translator.
- **Auto (player):**
  - `node --test` for the logic (`player/tests/lib.test.js`);
  - Playwright with the installed Google Chrome, emulating an iPhone (390×844, touch),
    in `player/tests/e2e/`.
- **Manual:** the user's real Chrome, driven through the Claude in Chrome extension.
- **Real generator run:** a one-minute English clip made with macOS `say`, run through
  mlx-whisper and then translated. The result is in `player/tests/e2e/fixtures/` and the
  e2e tests use it.

Totals:
- generator: 52 tests;
- player: 14 unit tests and 35 e2e tests.

Everything passes. The e2e suite passed three times in a row with no flaky tests.

## Generator (`listen-gen`)

| # | Scenario | Expected | Checked by | Result |
|---|---|---|---|---|
| G1 | Folder with an mp3, full run | `X.json`, `X.srt`, `X.ru.srt`, cache in `.listen-cache/` | auto + real run | ✅ |
| G2 | Splitting into lines | a line ends at 8 words or 5 seconds | auto | ✅ |
| G3 | A sentence spans several lines | the sentence is built from several lines; `from`/`to` point to its first and last word | auto + real run | ✅ |
| G4 | Abbreviations (`Dr.`, `Mr.`, `e.g.`) | they don't end a sentence | auto | ✅ |
| G5 | Text without full stops | split at 40 words, at a comma where possible | auto | ✅ |
| G6 | `--fix`: the LLM fixes recognition errors | the text changes, line timings stay the same | auto | ✅ |
| G7 | The LLM skips some items | the retry asks only for the missing ones; answers already received are kept | auto + real run | ✅ ⚠️ bug found |
| G8 | The LLM returns broken JSON, an empty value or an unknown id | retry; unknown ids are ignored | auto | ✅ |
| G9 | The LLM fails all 4 attempts | that file fails, the other files are still processed | auto | ✅ |
| G10 | Running again | finished files (those with `X.json`) are skipped; neither whisper nor the LLM is called | auto | ✅ |
| G11 | `--force` | the fix and the translation are redone; whisper output comes from the cache | auto | ✅ |
| G12 | `--retranscribe` | whisper runs again | auto | ✅ |
| G13 | Translation fails after `--fix` | the next run takes the fixed lines from the cache and doesn't fix them again | auto | ✅ |
| G14 | One file has no speech | that file fails, exit code 1 | auto | ✅ |
| G15 | `--src de --tgt uk --hint …` | the language goes to whisper, `X.uk.srt` is written, the hint goes into the LLM prompt | auto | ✅ |
| G16 | Hidden and non-audio files | ignored | auto | ✅ |
| G17 | Empty or missing folder | exit code 1 / 2 | auto | ✅ |
| G18 | The whisper model is not in the cache | an error, nothing is downloaded (`HF_HUB_OFFLINE=1`) | code review | ✅ |
| G19 | Real whisper on a `say` clip | words are recognized; every line has ≤ 8 words | auto (slow) | ✅ |

### macOS translator (the default)
| # | Scenario | Expected | Checked by | Result |
|---|---|---|---|---|
| G20 | Run with no options | one call to the macOS translator; the LLM client is never created; no fix cache; `X.json` has `fixed: false`, `translator: "apple"` | auto | ✅ |
| G21 | `--fix` | the LLM fixes the lines, then macOS translates the fixed text | auto | ✅ |
| G22 | `--translator llm` (with or without `--fix`) | fallback: the LLM translates, macOS is not called | auto | ✅ |
| G23 | Translation languages not downloaded | a clear message about where to download them; the whole run stops at once instead of failing every file | auto + real run | ✅ |
| G24 | Real macOS translation en→ru | Cyrillic output; a full `listen-gen` run without an LLM | auto (slow) + real run | ✅ 10 sentences in about 1 s, the whole file in 15 s (whisper output from the cache) |
| G25 | Swift helper errors: unsupported language, wrong number of results, empty translation, compile error | a clear error | auto | ✅ |
| G26 | Building the helper | built once and cached by a hash of the source; rebuilt when the source changes | auto | ✅ |

**Found in the real run (G7).** `gpt-4o-mini` kept leaving out short phrases such as
“Welcome back to the show” and “Let's start with the basics”, so all 4 attempts failed.
Two fixes:
- the prompt now says how many items to return and that short phrases count too;
- the retry asks only for the missing ids.

After the fix, all 10 sentences are translated on the first attempt.

**macOS vs `gpt-4o-mini` (G24), on the same 10 sentences.** The quality is about the
same, and macOS was slightly better in a few places:
- “Welcome back to the show” became «С возвращением на шоу» (natural) rather than
  «Добро пожаловать обратно в шоу» (word for word);
- the LLM made a grammar error, «наше мониторинг»; macOS wrote «наш мониторинг».

## Player

### Library and import
| # | Scenario | Expected | Checked by | Result |
|---|---|---|---|---|
| P1 | First launch | empty library with instructions | auto + Chrome | ✅ |
| P2 | Pick `X.json` and `X.mp3` | “Episodes added: 1”; a card with the title, duration and number of lines | auto + Chrome | ✅ |
| P3 | Only the json | “audio file not selected: X.mp3”; nothing is added | auto | ✅ |
| P4 | Only the mp3 | “missing X.json” | auto | ✅ |
| P5 | Broken json | an error message; nothing is added | auto | ✅ |
| P6 | json with a different format version | “unknown format version” | auto | ✅ |
| P7 | Importing the same episode again | no duplicate; the listening position is kept | auto | ✅ |
| P8 | Delete | the first tap shows “Sure?”, the second deletes; after 3 s the button resets | auto | ✅ |
| P9 | Delete and import again | the position starts over at 0:00 | auto | ✅ |
| P10 | Progress on the card | “0:20 / 0:37” and a progress bar | auto | ✅ |

### Playback
| # | Scenario | Expected | Checked by | Result |
|---|---|---|---|---|
| P11 | Open an episode | all lines and words, the duration, URL `#/ep/<id>` | auto + Chrome | ✅ |
| P12 | Play/Pause | time moves; exactly one current line is highlighted; the button shows ▶/❚❚ | auto + Chrome | ✅ |
| P13 | −1m / −10 / −5 / +5 / +10 / +1m | jumps, clamped to the start and end | auto | ✅ |
| P14 | Seek bar | the label changes while dragging; playback jumps on release | auto | ✅ |
| P15 | Tap a line's timestamp | jumps to that line and plays | auto | ✅ |
| P16 | Auto-scroll | the current line stays on screen | auto | ✅ |
| P17 | Manual scroll | auto-scroll waits 4 s before taking over again | code review | ✅ |

### Tap to translate
| # | Scenario | Expected | Checked by | Result |
|---|---|---|---|---|
| P18 | Tap a word while playing | playback pauses; the panel shows the word, the whole sentence with the word highlighted, and the translation; the whole sentence is highlighted in the list, across lines | auto + Chrome | ✅ |
| P19 | “Close” after tapping during playback | the panel closes, the highlight is removed, playback resumes | auto + Chrome | ✅ |
| P20 | Tap the dimmed background while paused | the panel closes, playback stays paused | auto | ✅ |
| P21 | Tap outside the panel, then another word | the first tap closes the panel, the second opens the new word's sentence | auto | ✅ |
| P22 | “↺ Replay sentence” | jumps to the start of the sentence (−0.15 s) and plays | auto | ✅ |
| P23 | Every word has a translation | no “—” anywhere in the episode | auto | ✅ |

### Settings and persistence
| # | Scenario | Expected | Checked by | Result |
|---|---|---|---|---|
| P24 | “Translation” | sentence translations appear under the line where each sentence ends; the setting survives a reload | auto + Chrome | ✅ |
| P25 | Speed 0.75–1.5× | cycles through the speeds; shared by all episodes; kept even after an immediate reload | auto + Chrome | ✅ ⚠️ bug found |
| P26 | Position | saved immediately on pause and every 5 s during playback; restored after a reload | auto | ✅ |
| P27 | Episode finished | the next time it opens, it starts at 0:00 | auto | ✅ ⚠️ bug found |
| P28 | “‹” and the browser Back button | back to the library, playback paused; history works | auto | ✅ |
| P29 | Unknown `#/ep/…` | the library opens | auto | ✅ |
| P30 | Lock screen | `mediaSession` with the title, play/pause and skip | auto (metadata) | ✅ |

### Offline and layout
| # | Scenario | Expected | Checked by | Result |
|---|---|---|---|---|
| P31 | No network after the first visit | the library, the episode and the audio all work | auto (offline) + Chrome (server stopped) | ✅ |
| P32 | Width 320 / 390 / 430 | no horizontal scrolling; all buttons on screen | auto | ✅ |
| P33 | Header while scrolling, light and dark theme | “‹”, “Translation” and the speed button stay visible and tappable | auto + Chrome | ✅ ⚠️ bug found |
| P34 | JS errors | none (every e2e test and the Chrome console check for errors) | auto + Chrome | ✅ |

**Bugs found and fixed:**
- **P25.** Speed and position were written to IndexedDB, which is asynchronous, so an
  immediate reload lost them. On an iPhone the same thing would happen if iOS closed the
  app right after a pause. Speed and position now go to localStorage, which writes
  synchronously.
- **P33.** Found manually in Chrome: when you scrolled, the header moved off screen and
  the Back, Translation and speed buttons disappeared. The cause was
  `overflow-x: hidden` on `body`, which breaks `position: sticky`. Fixed, with a test
  that fails on the old CSS.
- **P27.** When an episode had been played to the end, it showed 0:37 on opening but
  played from 0:00. Fixed.
- A small one, also found manually: the sentence highlight was too faint in the dark
  theme. It is now brighter.

## Not checked: needs a real iPhone
These can't be checked in Chrome on a Mac:
- **Home Screen install:** Share → Add to Home Screen, then launching without a network.
- **Background playback:**
  - does it keep playing with the screen locked and after switching to another app?
  - do the lock-screen and headphone controls work?
- **Picking several files in Files:** choosing the mp3 and the json in one go.
- **Seeking in long mp3s (an hour or more):** the audio is stored on the device and
  played from there.
- **Storage:** will iOS remove the data? The app asks for persistent storage with
  `navigator.storage.persist()`.
- **Updates:** the service worker serves the cached copy and updates in the background,
  so a new version appears on the second launch after a release. This is the case in
  Chrome and should be the same on an iPhone.
