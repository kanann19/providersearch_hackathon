"""The web server. Run:  python app.py   then open http://localhost:5000"""
import os
import uuid

from flask import Flask, jsonify, request, send_from_directory

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


@app.post("/api/chat")
def chat():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("message") or "").strip()[:1000]
    if not text:
        return jsonify({"error": "Please type or say what you need."}), 400
    sid = data.get("session") or str(uuid.uuid4())
    history = SESSIONS.setdefault(sid, [])
    try:
        return jsonify(agent.ask(history, text))
    except RuntimeError as e:          # for example: no API key yet
        return jsonify({"answer": str(e), "steps": [], "candidates": [], "error": str(e)})


@app.post("/api/draft")
def draft():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(T.draft_contact(data.get("id", ""), data.get("channel", "call"),
                                   data.get("reason") or "a new patient appointment"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
