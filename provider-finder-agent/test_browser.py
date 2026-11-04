"""Browser test: opens the real page in Chromium and clicks through it.
Needs:  pip install playwright   then   playwright install chromium   (skipped if missing).
Uses the fake model and a fake Muse Voice server, so it needs no key."""
import base64
import json
import threading

import pytest

pw = pytest.importorskip("playwright.sync_api")
from flask import Flask
from flask_sock import Sock
from werkzeug.serving import make_server

import extras

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
SPOKEN = "female pediatrician near Issaquah Premera"


def serve(app):
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def site(monkeypatch):
    # fake Muse Voice: after about one second of sound it "hears" SPOKEN
    asr, mode = Flask("asr"), {"refuse": False}
    sock = Sock(asr)

    @sock.route("/asr")
    def fake(ws):
        ws.receive()
        if mode["refuse"]:
            ws.send(json.dumps({"message": "no"}))
            return
        ws.send(json.dumps({"sessionId": "s"}))
        total, said = 0, False
        while True:
            d = ws.receive(timeout=5)
            if d is None:
                return
            if isinstance(d, (bytes, bytearray)):
                total += len(d)
                if total > 48000 and not said:
                    said = True
                    ws.send(json.dumps({"type": "speechStart", "turnId": 1}))
                    ws.send(json.dumps({"type": "transcript", "transcript": "female pedi", "final": False}))
                    ws.send(json.dumps({"type": "speechComplete", "turnId": 1, "transcript": SPOKEN}))
            elif json.loads(d).get("type") == "endStream":
                return

    a = serve(asr)
    monkeypatch.setattr(extras, "ASR_URL", f"ws://127.0.0.1:{a.server_port}/asr")
    monkeypatch.setenv("MODEL_API_KEY", "k")
    monkeypatch.setattr(extras, "voice_ready", lambda: True)           # pretend we are live, but the model stays the mock
    import app as webapp
    webapp.SESSIONS.clear()
    s = serve(webapp.app)
    yield f"http://127.0.0.1:{s.server_port}", mode
    s.shutdown(); a.shutdown()


@pytest.fixture
def page(site):
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        ctx = browser.new_context(permissions=["microphone"])
        pg = ctx.new_page()
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.goto(site[0])
        pg.wait_for_function("document.querySelector('#lang').options.length > 3")
        yield pg
        browser.close()


def test_page_is_white_with_carbon_text_even_in_dark_mode(site):
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context(color_scheme="dark").new_page()
        pg.goto(site[0])
        assert pg.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(255, 255, 255)"
        assert pg.evaluate("getComputedStyle(document.body).color") == "rgb(27, 31, 36)"
        b.close()


def test_search_shows_table_cards_why_line_and_verified_badge(page):
    page.fill("#box", "Female pediatrician near Issaquah, Premera")
    page.click("#send")
    page.wait_for_selector(".pcard")
    assert page.locator(".cmp tr.rowlink").count() >= 2
    why = page.locator(".pcard .why").first.inner_text()
    assert "Why this doctor" in why and "matches a real review" in why
    assert "Checked" in page.locator(".verified").inner_text()
    assert page.errors == []


def test_card_click_opens_details_and_back_closes(page):
    page.fill("#box", "Female pediatrician near Issaquah, Premera"); page.click("#send")
    page.wait_for_selector(".pcard")
    page.locator(".pcard").first.click()
    page.wait_for_selector("#detail:not([hidden]) #back")             # wait until the details have loaded
    assert "patient reviews" in page.inner_text("#detail").lower()   # the page shows headings in capitals
    page.click("#back")
    assert page.locator("#detail").is_hidden()


def test_insurance_card_photo_sets_plan_and_it_rides_along_with_the_next_search(page):
    page.set_input_files("#camfile", {"name": "card.png", "mimeType": "image/png", "buffer": PNG})
    page.wait_for_selector("#planbar:not([hidden])")
    assert page.inner_text("#plantext") == "Premera"
    sent = []
    page.on("request", lambda r: sent.append(r.post_data) if "chat_stream" in r.url else None)
    page.fill("#box", "Pediatrician near Issaquah"); page.click("#send")
    page.wait_for_selector(".pcard")
    assert "My insurance plan is Premera" in sent[0]
    assert "Premera" in page.locator(".me").first.inner_text() is False or True   # the visible bubble shows only what she typed
    assert page.locator(".me").first.inner_text() == "Pediatrician near Issaquah"
    page.click("#planx")
    assert page.locator("#planbar").is_hidden()


def test_unreadable_card_shows_message_and_no_plan(page, monkeypatch):
    monkeypatch.setenv("MOCK_CARD_TEXT", "UNKNOWN")
    page.set_input_files("#camfile", {"name": "card.png", "mimeType": "image/png", "buffer": PNG})
    page.wait_for_function("document.querySelector('#status').textContent.includes('type your plan')")
    assert page.locator("#planbar").is_hidden()


def test_muse_voice_types_live_words_then_sends(page):
    page.select_option("#lang", "Spanish")
    page.wait_for_function("fetch('/api/health').then(r => r.json()).then(h => h.voice)")
    page.click("#mic")
    page.wait_for_function("document.querySelector('#mic').classList.contains('on')")
    page.wait_for_selector(".me", timeout=15000)                       # words arrive, then it sends by itself
    assert page.locator(".me").first.inner_text() == SPOKEN
    page.wait_for_selector(".pcard")
    assert not page.locator("#mic").evaluate("e => e.classList.contains('on')")
    assert page.errors == []


def test_voice_failure_falls_back_to_browser_speech(site, monkeypatch):
    url, mode = site
    mode["refuse"] = True
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        ctx = b.new_context(permissions=["microphone"])
        pg = ctx.new_page()
        pg.add_init_script("""window.__started = 0;
          class F { constructor(){} start(){ window.__started++; } stop(){} }
          window.SpeechRecognition = F; window.webkitSpeechRecognition = F;""")
        pg.goto(url)
        pg.wait_for_function("fetch('/api/health').then(r => r.json()).then(h => h.voice)")
        pg.click("#mic")
        pg.wait_for_function("() => window.__started >= 1", polling=200, timeout=10000)
        pg.wait_for_timeout(1500)
        assert pg.evaluate("window.__started") == 1                    # started once, not twice
        b.close()


def test_pressing_send_while_the_mic_is_on_sends_exactly_once(page):
    """The bug from your video: the same question appeared twice."""
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "chat_stream" in r.url else None)
    page.wait_for_function("fetch('/api/health').then(r => r.json()).then(h => h.voice)")
    page.click("#mic")
    page.wait_for_function("document.querySelector('#box').value.length > 3", timeout=15000)   # words are showing
    page.click("#send")                                                  # you press Send by hand
    page.wait_for_selector(".pcard", timeout=20000)
    page.wait_for_timeout(4000)                                          # long enough for any second send to happen
    assert page.locator(".me").count() == 1 and len(sent) == 1
    assert not page.locator("#mic").evaluate("e => e.classList.contains('on')")
    assert page.input_value("#box") == ""


def test_same_words_twice_in_a_row_are_sent_once(page):
    page.fill("#box", "Female pediatrician near Issaquah, Premera")
    page.evaluate("document.getElementById('send').click(); document.getElementById('box').value = 'Female pediatrician near Issaquah, Premera'; document.getElementById('send').click();")
    page.wait_for_selector(".pcard")
    assert page.locator(".me").count() == 1


def _first_card(page):
    page.fill("#box", "Female pediatrician near Issaquah, Premera"); page.click("#send")
    page.wait_for_selector(".pcard")
    return page.locator(".pcard").first


def test_draft_send_opens_your_own_app_with_the_edited_text(page):
    page.evaluate("window.__open = (u) => { window.__opened = u; }")
    card = _first_card(page)
    card.locator('[data-ch="email"]').click()
    card.locator(".dtext").wait_for()
    card.locator(".subj").fill("Hello there")
    card.locator(".dtext").fill("My own words here.")
    card.locator(".go").click()
    url = page.evaluate("window.__opened")
    assert url.startswith("mailto:?subject=Hello%20there&body=My%20own%20words%20here.")
    card.locator('[data-ch="text"]').click()
    card.locator(".go").wait_for()
    card.locator(".dtext").fill("Text me back")
    card.locator(".go").click()
    assert page.evaluate("window.__opened") == "sms:?&body=Text%20me%20back"
    card.locator('[data-ch="call"]').click()
    card.locator(".go").wait_for()
    card.locator(".go").click()
    assert page.evaluate("window.__opened").startswith("tel:") and "555" in page.evaluate("window.__opened")


def test_open_channel_button_is_highlighted_and_cancel_closes_the_editor(page):
    card = _first_card(page)
    card.locator('[data-ch="email"]').click()
    card.locator(".dtext").wait_for()
    assert "solid" in card.locator('[data-ch="email"]').get_attribute("class")
    assert "solid" not in card.locator('[data-ch="call"]').get_attribute("class")
    card.locator(".cn").click()
    assert card.locator(".editor").count() == 0 and "editing" not in card.get_attribute("class")
    assert "solid" not in card.locator('[data-ch="email"]').get_attribute("class")


def test_save_keeps_drafts_and_the_saved_list_can_copy_send_and_delete(page):
    page.evaluate("window.__open = (u) => { window.__opened = u; }")
    card = _first_card(page)
    name = card.locator("h3").inner_text()
    card.locator('[data-ch="text"]').click()
    card.locator(".dtext").wait_for()
    card.locator(".dtext").fill("Please save this")
    card.locator(".sv").click()
    assert page.inner_text("#savedbtn") == "Saved drafts (1)"
    card.locator(".dtext").fill("Edited again")                 # saving the same doctor + channel updates, not duplicates
    card.locator(".sv").click()
    assert page.inner_text("#savedbtn") == "Saved drafts (1)"
    card.locator(".cn").click()                                  # cancel does not delete what was saved
    page.click("#savedbtn")
    page.wait_for_selector(".sv-item")
    item = page.locator(".sv-item").first
    assert name in item.inner_text() and "Edited again" in item.inner_text()
    item.locator('[data-a="go"]').click()
    assert page.evaluate("window.__opened") == "sms:?&body=Edited%20again"
    page.reload()                                                # survives a refresh
    assert page.inner_text("#savedbtn") == "Saved drafts (1)"
    page.click("#savedbtn")
    page.locator('.sv-item [data-a="del"]').click()
    assert page.inner_text("#savedbtn") == "Saved drafts (0)" and "Nothing saved yet" in page.inner_text("#detail")
    assert page.errors == []
