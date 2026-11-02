"""The web server. Run:  python app.py   then open http://localhost:5000"""
import json
import os
import queue
import threading
import uuid

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

import agent
import tools as T

app = Flask(__name__)
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
                    "providers": len(T.PROVIDERS)})


def _read_message():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("message") or "").strip()[:1000]
    sid = data.get("session") or str(uuid.uuid4())
    return text, SESSIONS.setdefault(sid, [])


@app.post("/api/chat")
def chat():
    text, history = _read_message()
    if not text:
        return jsonify({"error": "Please type or say what you need."}), 400
    try:
        return jsonify(agent.ask(history, text))
    except RuntimeError as e:          # for example: no API key yet
        return jsonify({"answer": str(e), "steps": [], "candidates": [], "error": str(e)})


@app.post("/api/chat_stream")
def chat_stream():
    """Same as /api/chat, but sends each step as it happens (for the live panel)."""
    text, history = _read_message()
    events = queue.Queue()

    def work():
        try:
            result = agent.ask(history, text, on_step=lambda s: events.put({"type": "step", "text": s}))
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


@app.post("/api/draft")
def draft():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(T.draft_contact(data.get("id", ""), data.get("channel", "call"),
                                   data.get("reason") or "a new patient appointment"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False, threaded=True)
