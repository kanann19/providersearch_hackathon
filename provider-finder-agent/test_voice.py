"""Voice relay test: a fake Muse Voice Transcribe server, our relay, and a fake browser.
Checks the full path: handshake, sound going up, words coming back, ending the stream."""
import json
import threading
import time

import pytest
import websocket
from flask import Flask
from flask_sock import Sock
from werkzeug.serving import make_server

import extras


def serve(app):
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def fake_muse(monkeypatch):
    """Pretends to be wss://api.meta.ai/v1/asr/realtime."""
    log = {"handshake": None, "audio": 0, "ended": False, "url": None}
    mode = {"refuse": False}
    app = Flask(__name__)
    sock = Sock(app)

    @sock.route("/asr")
    def asr(ws):
        from flask import request
        log["url"] = request.full_path
        log["handshake"] = json.loads(ws.receive())
        if mode["refuse"]:
            ws.send(json.dumps({"message": "bad key"}))
            return
        ws.send(json.dumps({"sessionId": "s1"}))
        sent_partial = False
        while True:
            d = ws.receive(timeout=3)
            if d is None:
                return
            if isinstance(d, (bytes, bytearray)):
                log["audio"] += len(d)
                if not sent_partial:
                    sent_partial = True
                    ws.send(json.dumps({"type": "speechStart", "turnId": 1}))
                    ws.send(json.dumps({"type": "transcript", "transcript": "sinus spec", "final": False, "secret": "x"}))
                    ws.send(json.dumps({"type": "diagnostics", "internal": True}))
            elif json.loads(d).get("type") == "endStream":
                log["ended"] = True
                ws.send(json.dumps({"type": "speechComplete", "turnId": 1, "transcript": "sinus specialist near Bellevue"}))
                return

    srv = serve(app)
    monkeypatch.setattr(extras, "ASR_URL", f"ws://127.0.0.1:{srv.server_port}/asr")
    monkeypatch.setenv("MODEL_API_KEY", "test-key-123")
    yield log, mode
    srv.shutdown()


@pytest.fixture
def our_server():
    app = Flask(__name__)
    sock = Sock(app)

    @sock.route("/ws/voice")
    def voice(ws):
        extras.voice_relay(ws, "Spanish")

    srv = serve(app)
    yield f"ws://127.0.0.1:{srv.server_port}/ws/voice"
    srv.shutdown()


def listen(browser, until, secs=5):
    got, end = [], time.time() + secs
    browser.settimeout(0.5)
    while time.time() < end:
        try:
            m = browser.recv()
        except websocket.WebSocketTimeoutException:
            continue
        except Exception:
            break
        got.append(json.loads(m))
        if got[-1].get("type") == until:
            break
    return got


def test_words_come_back_and_the_stream_ends_properly(fake_muse, our_server):
    log, _ = fake_muse
    b = websocket.create_connection(our_server)
    assert listen(b, "ready")[-1]["type"] == "ready"
    b.send_binary(b"\x01\x02" * 480)                                  # a little sound
    got = listen(b, "transcript")
    assert {"type": "transcript", "transcript": "sinus spec", "final": False} in got
    b.send("end")
    done = listen(b, "speechComplete")
    assert done[-1]["transcript"] == "sinus specialist near Bellevue"
    assert log["audio"] == 960 and log["ended"] is True
    b.close()


def test_handshake_carries_key_model_and_language_but_browser_never_sees_the_key(fake_muse, our_server):
    log, _ = fake_muse
    b = websocket.create_connection(our_server)
    seen = listen(b, "ready")
    b.send("end")
    seen += listen(b, "speechComplete")
    h = log["handshake"]
    assert h["authorization"]["accessToken"] == "Bearer test-key-123"
    assert h["languageBias"] == ["Spanish"] and h["audioEncoding"] == "PCM_24KHZ"
    assert "sessionId=stream-" in log["url"]
    assert "test-key-123" not in json.dumps(seen)


def test_only_safe_message_types_and_fields_reach_the_browser(fake_muse, our_server):
    b = websocket.create_connection(our_server)
    listen(b, "ready")
    b.send_binary(b"\x00\x01" * 100)
    got = listen(b, "never", secs=1.5)                                 # wait long enough for the junk message too
    assert any(m["type"] == "transcript" for m in got)
    assert all(m["type"] in extras.FORWARD | {"ready"} for m in got)          # "diagnostics" was dropped
    assert all("secret" not in m for m in got)


def test_refused_key_is_reported_as_an_error(fake_muse, our_server):
    _, mode = fake_muse
    mode["refuse"] = True
    b = websocket.create_connection(our_server)
    m = listen(b, "error")[-1]
    assert m["type"] == "error" and "bad key" in m["message"]


def test_unreachable_voice_service_is_reported_as_an_error(monkeypatch, our_server):
    monkeypatch.setattr(extras, "ASR_URL", "ws://127.0.0.1:9/asr")
    monkeypatch.setenv("MODEL_API_KEY", "k")
    m = listen(websocket.create_connection(our_server), "error")[-1]
    assert m["type"] == "error" and "not reachable" in m["message"]


def test_missing_key_is_reported_as_an_error(monkeypatch, our_server):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert listen(websocket.create_connection(our_server), "error")[-1]["message"] == "No API key"


def test_browser_closing_early_cleans_up(fake_muse, our_server):
    b = websocket.create_connection(our_server)
    listen(b, "ready")
    b.close()                                                          # must not hang or crash the server
    b2 = websocket.create_connection(our_server)
    assert listen(b2, "ready")[-1]["type"] == "ready"
