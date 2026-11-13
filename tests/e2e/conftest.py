"""E2E fixtures: serve player/ over HTTP and drive the installed Google Chrome
(channel="chrome" — no Playwright browser download) with an iPhone-sized,
touch-enabled viewport."""
import functools
import http.server
import json
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

PLAYER = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
EP_JSON = FIXTURES / "Episode 1.json"
EP_MP3 = FIXTURES / "Episode 1.mp3"


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".webmanifest": "application/manifest+json", ".js": "text/javascript"}

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(PLAYER)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    httpd.shutdown()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True,
                              args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"])
        yield b
        b.close()


@pytest.fixture
def context(browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, locale="en-US")
    yield ctx
    ctx.close()


@pytest.fixture
def page(context, server):
    pg = context.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(server)
    pg.wait_for_selector("#library:not([hidden])")
    yield pg
    assert errors == [], f"JS errors: {errors}"


@pytest.fixture(scope="session")
def episode():
    return json.loads(EP_JSON.read_text(encoding="utf-8"))


def import_files(page, *paths):
    page.set_input_files("#import", [str(p) for p in paths])


@pytest.fixture
def opened(page):
    """Episode imported and opened in the player, audio metadata loaded."""
    import_files(page, EP_JSON, EP_MP3)
    page.click(".ep-open")
    page.wait_for_selector("#player:not([hidden])")
    page.wait_for_function("document.getElementById('audio').readyState >= 1")
    return page


def audio_time(page) -> float:
    return page.evaluate("document.getElementById('audio').currentTime")


def is_paused(page) -> bool:
    return page.evaluate("document.getElementById('audio').paused")


def set_time(page, t: float):
    page.evaluate(f"(() => {{ const a = document.getElementById('audio'); a.pause(); a.currentTime = {t}; }})()")
    page.wait_for_function(f"Math.abs(document.getElementById('audio').currentTime - {t}) < 0.05")
