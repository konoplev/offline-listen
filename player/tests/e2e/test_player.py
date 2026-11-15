import json

import pytest

from conftest import EP_JSON, EP_MP3, audio_time, import_files, import_folder, is_paused, make_episode, set_time


def word_el(page, ci, wi):
    return page.locator(f'.cue[data-i="{ci}"] .w[data-w="{wi}"]')


def find_word(episode, word):
    for ci, c in enumerate(episode["cues"]):
        ws = c["t"].split()
        if word in ws:
            return ci, ws.index(word)
    raise AssertionError(word)


# ------------------------------------------------------------------ library

def test_empty_library_shows_instructions(page):
    assert page.locator("#empty").is_visible()
    assert "X.json" in page.inner_text("#empty")
    assert page.locator(".ep").count() == 0


def test_import_episode(page, episode):
    import_files(page, EP_JSON, EP_MP3)
    page.wait_for_selector(".ep")
    assert page.inner_text("#import-msg") == "Episodes added: 1"
    assert page.inner_text(".ep-title") == "Episode 1"
    assert f"{len(episode['cues'])} lines" in page.inner_text(".ep-meta")
    assert not page.locator("#empty").is_visible()


def test_import_json_without_audio_is_rejected(page):
    import_files(page, EP_JSON)
    page.wait_for_selector("#import-msg:not([hidden])")
    assert "audio file not selected: Episode 1.mp3" in page.inner_text("#import-msg")
    assert page.locator(".ep").count() == 0


def test_import_audio_without_json_is_rejected(page):
    import_files(page, EP_MP3)
    page.wait_for_selector("#import-msg:not([hidden])")
    assert "missing Episode 1.json" in page.inner_text("#import-msg")
    assert page.locator(".ep").count() == 0


def test_import_broken_json(page, tmp_path):
    bad = tmp_path / "Episode 1.json"
    bad.write_text("{not json", encoding="utf-8")
    import_files(page, bad, EP_MP3)
    page.wait_for_selector("#import-msg.error:not([hidden])")
    msg = page.inner_text("#import-msg")
    assert "Episode 1.json:" in msg and "missing Episode 1.json" in msg
    assert page.locator(".ep").count() == 0


def test_import_wrong_format_version(page, tmp_path, episode):
    bad = tmp_path / "Episode 1.json"
    bad.write_text(json.dumps({**episode, "version": 99}), encoding="utf-8")
    import_files(page, bad, EP_MP3)
    page.wait_for_selector("#import-msg:not([hidden])")
    assert "unknown format version: 99" in page.inner_text("#import-msg")


def test_reimport_replaces_without_duplicate_and_keeps_position(opened):
    page = opened
    set_time(page, 20)
    page.click("#back")
    page.wait_for_selector("#library:not([hidden])")
    assert page.inner_text(".ep-meta").startswith("0:20 /")
    import_files(page, EP_JSON, EP_MP3)
    page.wait_for_function("document.getElementById('import-msg').textContent.includes('Episodes added')")
    assert page.locator(".ep").count() == 1
    assert page.inner_text(".ep-meta").startswith("0:20 /")


def test_delete_needs_two_taps(page):
    import_files(page, EP_JSON, EP_MP3)
    page.wait_for_selector(".ep")
    page.click(".ep-del")
    assert page.inner_text(".ep-del") == "Sure?"
    assert page.locator(".ep").count() == 1
    page.click(".ep-del")
    page.wait_for_selector("#empty:not([hidden])")
    assert page.locator(".ep").count() == 0


def test_delete_confirmation_times_out(page):
    import_files(page, EP_JSON, EP_MP3)
    page.wait_for_selector(".ep")
    page.click(".ep-del")
    page.wait_for_function("document.querySelector('.ep-del').textContent === 'Delete'", timeout=5000)
    assert page.locator(".ep").count() == 1


# ------------------------------------------------------------------ player basics

def test_open_renders_all_cues_and_words(opened, episode):
    page = opened
    assert page.inner_text("#ep-title") == "Episode 1"
    assert page.locator(".cue").count() == len(episode["cues"])
    assert page.locator(".w").count() == sum(len(c["t"].split()) for c in episode["cues"])
    assert page.inner_text('.cue[data-i="0"]').startswith("0:00")
    assert page.inner_text("#dur") == "0:37"
    assert "#/ep/Episode%201" in page.url


def test_play_advances_and_highlights_current_cue(opened, episode):
    page = opened
    page.click("#play")
    page.wait_for_function("document.getElementById('audio').currentTime > 3.5")
    assert page.inner_text("#play") == "❚❚"
    active = int(page.get_attribute(".cue.active", "data-i"))
    t = audio_time(page)
    expected = max(i for i, c in enumerate(episode["cues"]) if c["s"] <= t)
    assert active in (expected, expected - 1)  # timeupdate fires every ~250ms
    assert page.locator(".cue.active").count() == 1
    page.click("#play")
    page.wait_for_function("document.getElementById('play').textContent === '▶'")
    assert is_paused(page)


def test_skip_buttons(opened):
    page = opened
    set_time(page, 20)
    page.click('[data-skip="5"]')
    assert audio_time(page) == pytest.approx(25, abs=0.1)
    page.click('[data-skip="-10"]')
    assert audio_time(page) == pytest.approx(15, abs=0.1)
    page.click('[data-skip="-60"]')
    assert audio_time(page) == pytest.approx(0, abs=0.1)
    page.click('[data-skip="60"]')
    dur = page.evaluate("document.getElementById('audio').duration")
    assert audio_time(page) == pytest.approx(dur, abs=0.1)
    page.click('[data-skip="-10"]')
    page.click('[data-skip="10"]')
    assert audio_time(page) == pytest.approx(dur, abs=0.1)


def test_seek_slider(opened):
    page = opened
    page.eval_on_selector("#seek", "el => { el.value = 30; el.dispatchEvent(new Event('input')); }")
    assert page.inner_text("#cur") == "0:30"
    page.eval_on_selector("#seek", "el => el.dispatchEvent(new Event('change'))")
    assert audio_time(page) == pytest.approx(30, abs=0.1)
    assert page.get_attribute(".cue.active", "data-i") is not None


def test_timestamp_tap_seeks_and_plays(opened, episode):
    page = opened
    page.click('.cue[data-i="5"] .ts')
    page.wait_for_function("!document.getElementById('audio').paused")
    assert audio_time(page) >= episode["cues"][5]["s"] - 0.05
    assert page.get_attribute(".cue.active", "data-i") == "5"


def test_auto_scroll_follows_playback(context, server):
    # short viewport so the list has to scroll
    page = context.new_page()
    page.set_viewport_size({"width": 390, "height": 420})
    page.goto(server)
    import_files(page, EP_JSON, EP_MP3)
    page.click(".ep-open")
    page.wait_for_function("document.getElementById('audio').readyState >= 1")
    set_time(page, 28)
    page.click("#play")
    page.wait_for_function("document.getElementById('audio').currentTime > 29")
    page.wait_for_function("window.scrollY > 100")
    box = page.locator(".cue.active").bounding_box()
    assert 0 < box["y"] < 420


# ------------------------------------------------------------------ word tap → sentence

def test_word_tap_pauses_and_shows_whole_sentence(opened, episode):
    page = opened
    # "Smith" is inside a sentence that spans cues 0..2
    ci, wi = find_word(episode, "Smith")
    sent = next(s for s in episode["sentences"] if s["t"].startswith("Today"))
    assert sent["from"][0] < ci < sent["to"][0] + 1

    page.click("#play")
    page.wait_for_function("!document.getElementById('audio').paused")
    word_el(page, ci, wi).click()

    assert is_paused(page)
    page.wait_for_selector("#sheet.open")
    assert page.inner_text("#s-word") == "Smith"
    assert page.inner_text("#s-orig") == sent["t"]
    assert page.inner_text("#s-orig mark") == "Smith"
    assert page.inner_text("#s-trans") == sent["tr"]
    # all words of the sentence are highlighted in the list, across cues
    assert page.locator(".w.in-sent").count() == len(sent["t"].split())
    assert page.locator(".w.sel").count() == 1


def test_closing_sheet_resumes_if_it_was_playing(opened, episode):
    page = opened
    page.click("#play")
    page.wait_for_function("!document.getElementById('audio').paused")
    word_el(page, *find_word(episode, "Smith")).click()
    assert is_paused(page)
    page.click("#s-close")
    page.wait_for_function("!document.getElementById('audio').paused")
    assert not page.locator("#sheet.open").count()
    assert page.locator(".w.in-sent, .w.sel").count() == 0


def test_closing_sheet_by_backdrop_keeps_pause_if_it_was_paused(opened, episode):
    page = opened
    word_el(page, *find_word(episode, "Smith")).click()
    page.wait_for_selector("#sheet.open")
    page.mouse.click(195, 100)  # backdrop
    page.wait_for_selector("#sheet:not(.open)")
    page.wait_for_timeout(300)
    assert is_paused(page)


def test_tap_outside_closes_sheet_then_next_word_opens_its_sentence(opened, episode):
    page = opened
    page.click("#play")
    page.wait_for_function("!document.getElementById('audio').paused")
    word_el(page, *find_word(episode, "Smith")).click()
    page.mouse.click(195, 100)  # tap on the list area hits the backdrop: closes + resumes
    page.wait_for_function("!document.getElementById('audio').paused")
    assert not page.locator("#sheet.open").count()
    word_el(page, 0, 0).click()
    assert page.inner_text("#s-orig") == episode["sentences"][0]["t"]
    assert page.locator(".w.sel").count() == 1
    assert page.locator(".w.in-sent").count() == len(episode["sentences"][0]["t"].split())
    page.click("#s-close")
    page.wait_for_function("!document.getElementById('audio').paused")


def test_replay_sentence(opened, episode):
    page = opened
    sent = episode["sentences"][4]
    ci, wi = sent["to"]
    set_time(page, 33)
    word_el(page, ci, wi).click()
    page.click("#s-replay")
    page.wait_for_function("!document.getElementById('audio').paused")
    t = audio_time(page)
    assert sent["s"] - 0.3 <= t <= sent["s"] + 0.6
    assert not page.locator("#sheet.open").count()


def test_every_word_has_a_sentence(opened, episode):
    page = opened
    missing = page.evaluate("""() => {
      const out = [];
      document.querySelectorAll('.cue').forEach(c => c.querySelectorAll('.w').forEach(w => {
        w.click();
        if (document.getElementById('s-trans').textContent === '—') out.push(c.dataset.i + ':' + w.dataset.w);
      }));
      document.getElementById('s-close').click();
      return out;
    }""")
    assert missing == []


# ------------------------------------------------------------------ settings & persistence

def test_translation_toggle_shows_inline_translations_and_persists(opened, episode):
    page = opened
    assert not page.locator(".tr").first.is_visible()
    page.click("#tr-toggle")
    assert page.locator(".tr").count() == len(episode["sentences"])
    assert page.locator(".tr").first.is_visible()
    assert page.inner_text(".tr >> nth=0") == episode["sentences"][0]["tr"]
    page.reload()
    page.wait_for_selector("#player:not([hidden])")
    assert page.locator("#tr-toggle.on").count() == 1
    assert page.locator(".tr").first.is_visible()


def test_speed_cycles_and_is_saved_immediately(opened):
    page = opened
    assert page.inner_text("#speed") == "1×"
    page.click("#speed")
    assert page.inner_text("#speed") == "1.15×"
    assert page.evaluate("document.getElementById('audio').playbackRate") == 1.15
    page.reload()  # right away: the setting must not depend on an async write
    page.wait_for_function("document.getElementById('audio').readyState >= 1")
    assert page.inner_text("#speed") == "1.15×"
    assert page.evaluate("document.getElementById('audio').playbackRate") == 1.15


def test_position_is_restored_after_reload(opened):
    page = opened
    page.click("#play")
    set_time(page, 21.5)  # pauses -> saves
    page.reload()  # immediately
    page.wait_for_function("document.getElementById('audio').currentTime > 21")
    assert audio_time(page) == pytest.approx(21.5, abs=0.2)
    assert page.inner_text("#cur") == "0:21"


def test_back_button_and_history(opened):
    page = opened
    page.click("#back")
    page.wait_for_selector("#library:not([hidden])")
    assert is_paused(page)
    page.go_back()
    page.wait_for_selector("#player:not([hidden])")
    page.go_back()
    page.wait_for_selector("#library:not([hidden])")


def test_unknown_episode_url_falls_back_to_library(page, server):
    page.goto(server + "#/ep/nope")
    page.wait_for_function("!location.hash.includes('nope')")  # after the failed lookup in IndexedDB
    assert page.locator("#library").is_visible()


def test_media_session_metadata(opened):
    assert opened.evaluate("navigator.mediaSession.metadata.title") == "Episode 1"


# ------------------------------------------------------------------ offline & layout

def test_works_offline_after_first_visit(context, server):
    page = context.new_page()
    page.goto(server)
    page.wait_for_function("navigator.serviceWorker.controller !== null || (location.reload(), false)",
                           timeout=10000, polling=1000)
    import_files(page, EP_JSON, EP_MP3)
    page.wait_for_selector(".ep")
    context.set_offline(True)
    try:
        page.reload()
        page.wait_for_selector(".ep")
        page.click(".ep-open")
        page.click("#play")
        page.wait_for_function("document.getElementById('audio').currentTime > 1")
        assert page.locator(".cue").count() > 0
    finally:
        context.set_offline(False)


@pytest.mark.parametrize("width", [320, 390, 430])
def test_no_horizontal_overflow(opened, width):
    page = opened
    page.set_viewport_size({"width": width, "height": 700})
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    for sel in ["#play", '[data-skip="-60"]', '[data-skip="60"]', "#speed", "#tr-toggle", "#prev", "#next"]:
        box = page.locator(sel).bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width, sel


def test_delete_forgets_position(opened):
    page = opened
    set_time(page, 20)
    page.click("#back")
    page.wait_for_selector("#library:not([hidden])")
    page.click(".ep-del")
    page.click(".ep-del")
    page.wait_for_selector("#empty:not([hidden])")
    import_files(page, EP_JSON, EP_MP3)
    page.wait_for_selector(".ep")
    assert page.inner_text(".ep-meta").startswith("0:00 /")


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_header_stays_on_screen_while_scrolling(context, server, scheme):
    page = context.new_page()
    page.emulate_media(color_scheme=scheme)
    page.set_viewport_size({"width": 390, "height": 420})
    page.goto(server)
    import_files(page, EP_JSON, EP_MP3)
    page.click(".ep-open")
    page.wait_for_selector("#player:not([hidden])")
    page.click("#tr-toggle")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_function("window.scrollY > 200")
    for sel in ["#back", "#speed", "#tr-toggle"]:
        box = page.locator(sel).bounding_box()
        assert 0 <= box["y"] < 80, sel
    page.click("#back")  # must be clickable, not covered or scrolled away
    page.wait_for_selector("#library:not([hidden])")


def test_finished_episode_starts_over(opened):
    page = opened
    dur = page.evaluate("document.getElementById('audio').duration")
    set_time(page, dur - 0.5)
    page.reload()
    page.wait_for_function("document.getElementById('audio').readyState >= 1")
    assert audio_time(page) == pytest.approx(0, abs=0.1)
    assert page.inner_text("#cur") == "0:00"


# ------------------------------------------------------------------ add menu, folder import

def test_add_menu_offers_folder_and_files(page):
    assert not page.locator("#add-menu").is_visible()
    page.click("#import-btn")
    assert page.locator("#add-menu").is_visible()
    assert "Folder" in page.inner_text("#add-menu") and "Files" in page.inner_text("#add-menu")
    assert page.get_attribute("label[for=import-dir]", "for") == "import-dir"
    assert page.evaluate("document.getElementById('import-dir').webkitdirectory")
    page.click("h1")
    assert not page.locator("#add-menu").is_visible()


def test_import_folder_matches_json_by_name(page, tmp_path):
    pods = tmp_path / "pods"
    make_episode(pods, "Episode 10")
    make_episode(pods, "Episode 2", ext="m4a")
    (pods / "Episode 2.mp3").write_bytes(EP_MP3.read_bytes())  # VBR source next to the generator's m4a
    (pods / "Episode 2.srt").write_text("1\n", encoding="utf-8")
    (pods / "Extra.mp3").write_bytes(EP_MP3.read_bytes())
    import_folder(page, pods)
    page.wait_for_selector(".ep")
    msg = page.inner_text("#import-msg")
    assert msg.splitlines() == ["Episodes added: 2", "Extra.mp3: missing Extra.json"]
    assert [t.strip() for t in page.locator(".ep-title").all_inner_texts()] == ["Episode 2", "Episode 10"]
    assert page.inner_text("#orphans") == "Pick JSON for Extra.mp3"

    import_folder(page, pods)  # again: nothing is copied twice
    page.wait_for_function("document.getElementById('import-msg').textContent.includes('Already')")
    assert page.inner_text("#import-msg").splitlines()[0] == "Already in the library: 2"
    assert page.locator(".ep").count() == 2


def test_import_folder_with_no_audio(page, tmp_path):
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    import_folder(page, tmp_path)
    page.wait_for_selector("#import-msg.error:not([hidden])")
    assert page.inner_text("#import-msg") == "No audio files in this folder"


def test_pick_json_for_audio_without_one(page):
    import_files(page, EP_MP3)
    page.wait_for_selector("#orphans:not([hidden])")
    assert page.locator(".ep").count() == 0
    with page.expect_file_chooser() as fc:
        page.click("text=Pick JSON for Episode 1.mp3")
    fc.value.set_files(str(EP_JSON))
    page.wait_for_selector(".ep")
    assert page.inner_text("#import-msg") == "Episodes added: 1"
    assert page.locator("#orphans").is_hidden()


# ------------------------------------------------------------------ playlist

@pytest.fixture
def two(page, tmp_path):
    """Episode 1 and Episode 2 in the library, Episode 1 open."""
    make_episode(tmp_path, "Episode 1")
    make_episode(tmp_path, "Episode 2")
    import_folder(page, tmp_path)
    page.wait_for_function("document.querySelectorAll('.ep').length === 2")
    page.click(".ep-open >> text=Episode 1")
    page.wait_for_selector("#player:not([hidden])")
    page.wait_for_function("document.getElementById('audio').readyState >= 1")
    page.wait_for_function("!document.getElementById('next').disabled")
    return page


def test_next_episode_starts_when_one_ends(two):
    page = two
    dur = page.evaluate("document.getElementById('audio').duration")
    set_time(page, dur - 1)
    page.click("#play")
    page.wait_for_function("document.getElementById('ep-title').textContent === 'Episode 2'", timeout=10000)
    assert "#/ep/Episode%202" in page.url
    page.wait_for_function("document.getElementById('audio').currentTime > 0.5")
    assert not is_paused(page)
    assert page.locator(".cue").count() > 0
    page.click("#back")
    page.wait_for_selector(".ep.done")  # the list is re-rendered asynchronously
    assert page.locator(".ep.done .ep-title").all_inner_texts() == ["Episode 1"]


def test_last_episode_ends_and_stops(two):
    page = two
    page.click("#next")
    page.wait_for_function("document.getElementById('ep-title').textContent === 'Episode 2'")
    assert page.is_disabled("#next") and not page.is_disabled("#prev")
    page.wait_for_function("document.getElementById('audio').readyState >= 1")
    dur = page.evaluate("document.getElementById('audio').duration")
    set_time(page, dur - 1)
    page.click("#play")
    page.wait_for_function("document.getElementById('audio').ended && document.getElementById('audio').paused")
    page.wait_for_timeout(500)  # nothing else starts
    assert page.inner_text("#ep-title") == "Episode 2"
    assert is_paused(page)


def test_prev_next_buttons_keep_play_state(two):
    page = two
    assert page.is_disabled("#prev")
    page.click("#next")  # paused stays paused
    page.wait_for_function("document.getElementById('ep-title').textContent === 'Episode 2'")
    assert is_paused(page)
    page.click("#play")
    page.wait_for_function("!document.getElementById('audio').paused")
    page.click("#prev")  # playing keeps playing
    page.wait_for_function("document.getElementById('ep-title').textContent === 'Episode 1'")
    page.wait_for_function("document.getElementById('audio').currentTime > 0.3")
    assert not is_paused(page)
    assert "#/ep/Episode%201" in page.url
    page.click("#back")
    page.wait_for_selector("#library:not([hidden])")


def test_media_session_track_actions(two):
    page = two
    page.evaluate("""() => {
        window.__h = {};
        const orig = navigator.mediaSession.setActionHandler.bind(navigator.mediaSession);
        navigator.mediaSession.setActionHandler = (k, fn) => { window.__h[k] = fn; orig(k, fn); };
    }""")
    page.click("#next")
    page.wait_for_function("document.getElementById('ep-title').textContent === 'Episode 2'")
    page.wait_for_function("window.__h.previoustrack")
    page.evaluate("window.__h.previoustrack()")
    page.wait_for_function("document.getElementById('ep-title').textContent === 'Episode 1'")


# ------------------------------------------------------------------ broken update

def test_broken_app_cache_offers_reload_and_keeps_episodes(context, server):
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(server)
    page.wait_for_function("navigator.serviceWorker.controller !== null || (location.reload(), false)",
                           timeout=10000, polling=1000)
    import_files(page, EP_JSON, EP_MP3)
    page.wait_for_selector(".ep")
    assert page.locator("#boot-fail").is_hidden()
    # a half-updated cache: new app.js next to an old lib.js without the exports it needs
    page.evaluate("""async () => {
        for (const k of await caches.keys()) {
            const c = await caches.open(k);
            await c.put('lib.js', new Response('export const old = 1;', {headers: {'content-type': 'text/javascript'}}));
        }
    }""")
    page.reload()
    page.wait_for_selector("#boot-fail:not([hidden])", timeout=8000)
    assert page.locator("#library").is_hidden()
    assert errors  # the module failed to load
    page.click("#boot-reload")
    page.wait_for_selector(".ep", timeout=10000)
    assert page.locator(".ep").count() == 1  # episodes survive
    assert page.locator("#boot-fail").is_hidden()


def test_app_files_come_from_one_cached_set(context, server):
    page = context.new_page()
    page.goto(server)
    page.wait_for_function("navigator.serviceWorker.controller !== null || (location.reload(), false)",
                           timeout=10000, polling=1000)
    names = page.evaluate("""async () => {
        const c = await caches.open((await caches.keys())[0]);
        return (await c.keys()).map((r) => new URL(r.url).pathname.split('/').pop());
    }""")
    assert sorted(names) == sorted(["", "index.html", "app.js", "lib.js", "db.js", "app.css",
                                    "manifest.webmanifest", "icon-180.png", "icon-512.png"])
    page.reload()  # served from the set: nothing is re-cached one file at a time
    page.wait_for_selector("#library:not([hidden])")
    assert page.evaluate("window.listenReady") is True
