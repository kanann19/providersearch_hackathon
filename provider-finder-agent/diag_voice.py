"""Checks the voice path WITHOUT the browser. Start the app first (python app.py), then run:  python diag_voice.py"""
import json, websocket
ws = websocket.create_connection("ws://127.0.0.1:5000/ws/voice?lang=English", timeout=12)
print("connected to our server")
try:
    for _ in range(3):
        print("server said:", ws.recv())
except Exception as e:
    print("stopped:", type(e).__name__, e)
