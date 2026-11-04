"""The web server. Run:  python app.py   then open http://localhost:5000"""
import json
import os
import queue
import threading
import uuid

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

import agent
import extras
import tools as T

app = Flask(__name__)
try:                                   # live voice needs flask-sock; the app still works without it
    from flask_sock import Sock
    sock = Sock(app)
except ImportError:
    sock = None
HERE = os.path.dirname(os.path.abspath(__file__))
SESSIONS = {}          # one conversation history per visitor


@app.get("/")
def home():
    return send_from_directory(HERE, "index.html")


@app.get("/api/health")
def health():
    mock = os.getenv("MOCK_MODEL") == "1"
    return jsonify({"mode": "mock" if mock else "live",
                    "key_set": bool(os.getenv("MODEL_API_KEY")), "model": agent.MODEL,
                    "providers": len(T.PROVIDERS),
                    "voice": extras.voice_ready() and sock is not None,
                    "languages": extras.LANGUAGES})


def _read_message():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("message") or "").strip()[:1000]
    sid = data.get("session") or str(uuid.uuid4())
    lang = data.get("language") if data.get("language") in extras.LANGUAGES else None
    return text, SESSIONS.setdefault(sid, []), lang


@app.post("/api/chat")
def chat():
    text, history, lang = _read_message()
    if not text:
        return jsonify({"error": "Please type or say what you need."}), 400
    try:
        return jsonify(agent.ask(history, text, language=lang))
    except RuntimeError as e:          # for example: no API key yet
        return jsonify({"answer": str(e), "steps": [], "candidates": [], "error": str(e)})


@app.post("/api/chat_stream")
def chat_stream():
    """Same as /api/chat, but sends each step as it happens (for the live panel)."""
    text, history, lang = _read_message()
    events = queue.Queue()

    def work():
        try:
            result = agent.ask(history, text, on_step=lambda s: events.put({"type": "step", "text": s}), language=lang)
        except RuntimeError as e:
            result = {"answer": str(e), "steps": [], "candidates": [], "error": str(e)}
        except Exception as e:
            result = {"answer": "Sorry, something went wrong. Please try again.", "steps": [],
                      "candidates": [], "error": str(e)}
        events.put({"type": "final", "data": result})
        events.put(None)

    if not text:
        events.put({"type": "final", "data": {"answer": "Please type or say what you need.",
                                              "steps": [], "candidates": []}})
        events.put(None)
    else:
        threading.Thread(target=work, daemon=True).start()

    def stream():
        while True:
            ev = events.get()
            if ev is None:
                break
            yield json.dumps(ev) + "\n"

    return Response(stream_with_context(stream()), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/provider/<pid>")
def provider(pid):
    """Everything about one provider, for the details panel. Plain code, no AI."""
    p = T._get(pid)
    if not p:
        return jsonify({"error": "not found"}), 404
    return jsonify({k: p[k] for k in ("id", "name", "gender", "specialty", "focus", "treats_kids", "city",
                                      "phone", "telehealth", "languages", "insurance", "accepting_new",
                                      "next_available", "reviews", "community_posts")})


@app.post("/api/draft")
def draft():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(T.draft_contact(data.get("id", ""), data.get("channel", "call"),
                                   data.get("reason") or "a new patient appointment"))


@app.post("/api/insurance_card")
def insurance_card():
    """Muse reads the plan name off a card photo. Only the plan name is returned; the photo is not saved."""
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(extras.read_card(data.get("image")))


if sock:
    @sock.route("/ws/voice")
    def voice(ws):
        lang = request.args.get("lang", "English")
        extras.voice_relay(ws, lang if lang in extras.LANGUAGES else "English")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False, threaded=True)
