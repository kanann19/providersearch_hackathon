"""extras.py: two extra Muse features, in plain words.

1. Insurance card photo.  Muse Spark LOOKS at the photo and tells us the insurance company.
   Our code then matches that to a plan name in our list. Nothing else is kept:
   no member ID, no name, no photo saved. Only a plan name like "Premera" leaves this file.

2. Voice.  Your browser sends microphone sound to our server, our server passes it to
   Muse Voice Transcribe, and the words come back live. The API key stays on the server.
"""
import json
import os
import re
import threading
import time
import uuid

import tools as T

# ---------- 1. Insurance card photo ----------

# Words on a card -> the plan name used in providers.json
PLAN_WORDS = {
    "Premera": ["premera"],
    "Regence": ["regence"],
    "Cigna": ["cigna"],
    "Aetna PPO": ["aetna"],
    "UnitedHealthcare": ["unitedhealthcare", "united healthcare", "uhc"],
    "Apple Health": ["apple health", "medicaid", "coordinated care"],
}
MAX_IMAGE_CHARS = 8_000_000          # about 6 MB of photo
IMAGE_OK = re.compile(r"^data:image/(png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=]+$")

CARD_PROMPT = ("This is a photo of a health insurance card. Tell me ONLY the name of the insurance "
               "company or plan printed on it (for example: Premera Blue Cross). Do NOT read, copy or "
               "repeat any numbers, member names or IDs. Reply with just the company name, or the word "
               "UNKNOWN if you cannot tell.")


def known_plans():
    """Plans that really exist in our provider list."""
    return {i for p in T.PROVIDERS for i in p["insurance"]}


PLAN_NAMES = {"premera": "Premera", "regence": "Regence", "cigna": "Cigna", "aetna": "Aetna",
              "unitedhealthcare": "UnitedHealthcare"}


def snap_plan_names(text):
    """Voice often mishears plan names ("Premara"). Plain code: a word that is very close to ONE plan name
    (and is not that exact word) becomes the real name. Other words are never touched."""
    import difflib
    out = []
    for w in re.split(r"(\W+)", text or ""):
        hit = difflib.get_close_matches(w.lower(), PLAN_NAMES, n=1, cutoff=0.78) if len(w) >= 5 else []
        out.append(PLAN_NAMES[hit[0]] if hit else w)
    return "".join(out)


def match_plan(text):
    """Turn what Muse said into one plan from our list, or None. Plain code, so it is exact.
    If the text matches two different plans, it is unclear, so we answer None."""
    low = (text or "").lower()
    hits = {plan for plan, words in PLAN_WORDS.items() if any(w in low for w in words)}
    hits &= known_plans()
    return hits.pop() if len(hits) == 1 else None


def read_card(image_data_url):
    """Look at an insurance card photo. Returns {"plan": name or None, "message": text}."""
    if not isinstance(image_data_url, str) or len(image_data_url) > MAX_IMAGE_CHARS:
        return {"plan": None, "message": "That photo is too big. Try a smaller one."}
    if not IMAGE_OK.match(image_data_url):
        return {"plan": None, "message": "Please use a PNG, JPG or WebP photo."}

    if os.getenv("MOCK_MODEL") == "1":                       # offline testing only
        said = os.getenv("MOCK_CARD_TEXT", "Premera Blue Cross")
    else:
        import agent                                          # same Muse client as the chat
        try:
            client = agent.get_client()
            kwargs = dict(model=agent.MODEL, max_completion_tokens=2000, reasoning_effort="low",
                          messages=[{"role": "user", "content": [
                              {"type": "text", "text": CARD_PROMPT},
                              {"type": "image_url", "image_url": {"url": image_data_url}}]}])
            said = (agent._call_model(client, kwargs).choices[0].message.content or "")
        except Exception as e:
            return {"plan": None, "message": "I couldn't read the photo just now. Please type your plan.",
                    "error": type(e).__name__}

    plan = match_plan(said)
    if plan:
        return {"plan": plan, "message": f"Looks like {plan}. I only kept the plan name."}
    return {"plan": None, "message": "I couldn't match that card to a plan in our sample list. Please type your plan."}


# ---------- 2. Voice (Muse Voice Transcribe) ----------

ASR_URL = os.getenv("ASR_URL", "wss://api.meta.ai/v1/asr/realtime")
ASR_MODEL = "muse-voice-transcribe-1.0"
LANGUAGES = ["English", "Spanish", "Hindi", "Telugu", "Tamil", "Mandarin", "Korean", "Vietnamese", "Arabic"]
FORWARD = {"transcript", "speechStart", "speechEnd", "speechComplete", "error"}   # what the browser may see
MAX_SECONDS = 90


def voice_ready():
    return bool(os.getenv("MODEL_API_KEY")) and os.getenv("MOCK_MODEL") != "1"


def keyword_list():
    """Words Muse Voice should listen for: provider names, cities, plans, focus areas. Helps with names like 'Hiro Quincy'."""
    words = []
    for p in T.PROVIDERS:
        words.append(p["name"].replace("Dr. ", ""))
    words += [c.title() for c in T.CITIES] + sorted(known_plans())
    words += sorted({f for p in T.PROVIDERS for f in p["focus"]})
    seen, out = set(), []
    for w in words:
        if w.lower() not in seen:
            seen.add(w.lower()); out.append(w)
    return out[:300]


def handshake(key, language, keywords=None):
    msg = {"authorization": {"accessToken": f"Bearer {key}"}, "audioEncoding": "PCM_24KHZ",
           "model": ASR_MODEL, "mode": "ENDPOINTING", "partialMode": "CUMULATIVE",
           "emitAudioProgress": False}
    if language in LANGUAGES:
        msg["languageBias"] = ["Mandarin Chinese" if language == "Mandarin" else language]
    if keywords:
        msg["keywords"] = keywords
    return msg


def voice_relay(ws, language="English"):
    """Pass sound from the browser to Muse Voice Transcribe, and words back.
    Browser sends: binary sound chunks (16-bit, 24 kHz, mono), then the text 'end'."""
    import websocket                                             # websocket-client
    from simple_websocket import ConnectionClosed

    def tell(obj):
        if obj.get("type") == "error":
            print(f"[voice] problem: {obj.get('message')}", flush=True)
        try:
            ws.send(json.dumps(obj))
        except Exception as e:
            print(f"[voice] could not tell the browser ({type(e).__name__})", flush=True)
        if obj.get("type") == "error":
            time.sleep(0.5)                       # let the message reach the browser before the connection closes

    key = os.getenv("MODEL_API_KEY")
    if not key:
        return tell({"type": "error", "message": "No API key"})
    up = None
    # Name hints (provider names, cities) are OFF by default: they are an extra that can make the service
    # hang up. Turn on with VOICE_KEYWORDS=1. If the service refuses them we retry plain.
    for kw in ((keyword_list(), None) if os.getenv("VOICE_KEYWORDS") == "1" else (None,)):
        try:
            up = websocket.create_connection(f"{ASR_URL}?sessionId=stream-{uuid.uuid4()}", timeout=10,
                                           header=["User-Agent: CareScout/1.0 (Meta hackathon)"])
            up.send(json.dumps(handshake(key, language, kw)))
            ack = json.loads(up.recv())
        except Exception as e:
            return tell({"type": "error", "message": f"Voice service not reachable ({type(e).__name__})"})
        if "sessionId" in ack:
            break
        try:
            up.close()
        except Exception:
            pass
        up = None
        last = ack
    if up is None:
        return tell({"type": "error", "message": str(last.get("message", "Voice service refused"))[:120]})

    print("[voice] Muse Voice Transcribe connected", flush=True)
    tell({"type": "ready"})
    up.settimeout(None)                 # the reader thread simply waits; closing the connection wakes it up
    done = threading.Event()

    def pump():                                                   # Muse -> browser
        while not done.is_set():
            try:
                frame = up.recv_data_frame(True)
                if frame[0] == websocket.ABNF.OPCODE_CLOSE:      # Muse hung up: say why
                    code = int.from_bytes(frame[1].data[:2], "big") if len(frame[1].data) >= 2 else None
                    print(f"[voice] Muse closed the connection. code={code} reason={frame[1].data[2:].decode('utf-8', 'replace')[:150]!r}", flush=True)
                    break
                raw = frame[1].data.decode("utf-8", "replace") if frame[0] == websocket.ABNF.OPCODE_TEXT else b""
            except Exception as e:
                if not done.is_set():
                    print(f"[voice] Muse connection ended: {type(e).__name__} {str(e)[:100]}", flush=True)
                break
            if not raw:                                            # binary frame or empty: nothing for us
                continue
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            if m.get("type") == "error":
                print(f"[voice] Muse error: {str(m)[:200]}", flush=True)
            if m.get("type") in FORWARD:
                tell({k: m[k] for k in ("type", "transcript", "final", "message", "turnId") if k in m})
        done.set()

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    started, ended_at = time.time(), None
    try:
        while not done.is_set() and time.time() - started < MAX_SECONDS:
            if ended_at and time.time() - ended_at > 4:           # gave Muse a moment to finish
                break
            try:
                data = ws.receive(timeout=0.3)
            except ConnectionClosed:
                print("[voice] browser closed the connection", flush=True)
                break
            if data is None:
                continue
            if isinstance(data, (bytes, bytearray)):
                up.send_binary(bytes(data))
            elif data == "end" and not ended_at:
                up.send(json.dumps({"type": "endStream"}))
                ended_at = time.time()
    except Exception as e:
        print(f"[voice] relay stopped: {type(e).__name__} {str(e)[:120]}", flush=True)
    finally:
        if ended_at is None and not (time.time() - started >= MAX_SECONDS):
            tell({"type": "error", "message": "Muse voice stopped. Please try again"})
        done.set()
        try:
            up.close()
        except Exception:
            pass
