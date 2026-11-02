"""agent.py: the brain of the app, in plain words.

What happens when someone asks for a doctor:
  1. We send the request to Muse, plus a list of tools it is allowed to use.
  2. Muse picks a tool (for example: search providers). Our code runs it and
     sends the result back to Muse.
  3. Muse looks at the result, then picks the next tool or writes the final answer.
     This back-and-forth is called the "agent loop".
  4. Before showing the answer, checks.py confirms every doctor name and every
     quote is real (it came from a tool).

Muse does the thinking. Our code does the exact work and the checking.
"""
import json
import os
import time
from datetime import date

import checks
import tools as T

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.getenv("MODEL_NAME", "muse-spark-1.3")
MAX_TURNS = 10          # stop the loop after this many model calls
RUN_LOG_DIR = os.path.join(HERE, "runs")


def load_env():
    """Read MODEL_API_KEY from a .env file so you never paste it into code."""
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()


def get_client():
    if os.getenv("MOCK_MODEL") == "1":          # only for offline testing
        from mock_model import MockClient
        return MockClient()
    key = os.getenv("MODEL_API_KEY")
    if not key:
        raise RuntimeError("MODEL_API_KEY is missing. Put it in the .env file.")
    from openai import OpenAI                    # Meta's API works with this library
    return OpenAI(base_url=os.getenv("MODEL_API_BASE_URL") or "https://api.meta.ai/v1",
                  api_key=key, max_retries=4, timeout=180)


SYSTEM = """You are a provider-finder assistant. You help people find a doctor or clinic
from a SAMPLE database, using the tools you are given. Today is {today}.

Rules:
- You find providers. You NEVER diagnose, never name a condition, never give medical advice.
  If the person describes an emergency, tell them to call 911 and stop.
- Use only facts returned by tools. Never invent a doctor, date, phone number, or review.
- Ask for missing details only if you truly need them: you need at least a type of doctor
  (or a focus like "sinus problems") and a city. Insurance is the plan name only
  (like "Aetna PPO"). Never ask for a member ID. Ask ONE short question at a time.
- Match what the person needs to a doctor's "focus" list. Use the focus filter for
  specifics like adenoids, sinus, PCOS, asthma, ADHD.
- If nothing matches, widen the distance or drop one filter, and say what you changed.
- If a doctor is not accepting new patients, use find_alternatives and say so.
- For your top 2-3 picks: check_availability, then get_reviews (and get_community_mentions).
- Then call compare_providers ONCE to score those picks side by side. Scores are 1-5
  (5 is best) for: short wait, easy to reach by phone, listens well. Base scores only on
  the reviews; use 3 when the reviews do not say. Each row needs one EXACT quote copied
  word for word from that provider's reviews. Rank the rows by what the person said
  matters most (soonest, closest, short waits...). If the tool refuses a quote, fix it.
- After the comparison, write a SHORT final answer: your top pick and one line why, plus
  any change you made (like widening the distance). Do not repeat the whole table.
  Any quote in your answer must also be word for word from a review.
- Only draft a call script / text / email if asked. You never send anything.
- Keep answers short and plain. No long paragraphs. Use the exact doctor names from tools.
- Dates and reviews are sample data. Mention that once, briefly, if relevant."""

TOOL_DEFS = [
    {"type": "function", "function": {
        "name": "search_providers",
        "description": "Find providers matching filters. Empty filters are ignored. Sorted by soonest appointment.",
        "parameters": {"type": "object", "properties": {
            "specialty": {"type": "string", "description": "e.g. Pediatrics, Primary Care, ENT, OB-GYN, Endocrinology, Orthopedics, Dermatology, Cardiology, Neurology, Physical Therapy, Sports Medicine, Gastroenterology, Pulmonology"},
            "focus": {"type": "string", "description": "Sub-specialty keyword, e.g. sinus, adenoids, PCOS, asthma, ADHD, eczema, knee"},
            "city": {"type": "string", "description": "City the person is near, e.g. Issaquah"},
            "max_miles": {"type": "number", "description": "Max distance in miles from the city"},
            "insurance": {"type": "string", "description": "Plan name, e.g. Aetna PPO, Premera, Cigna, Regence, UnitedHealthcare, Apple Health"},
            "gender": {"type": "string", "enum": ["female", "male"]},
            "kids": {"type": "boolean", "description": "true if the patient is a child"},
            "telehealth": {"type": "boolean"},
            "language": {"type": "string"},
            "accepting_new": {"type": "boolean", "description": "default true"}}}}},
    {"type": "function", "function": {
        "name": "check_availability",
        "description": "Next open appointment dates for one provider.",
        "parameters": {"type": "object", "properties": {
            "provider_id": {"type": "string"},
            "before_date": {"type": "string", "description": "YYYY-MM-DD, optional"}},
            "required": ["provider_id"]}}},
    {"type": "function", "function": {
        "name": "get_reviews",
        "description": "Patient reviews for one provider.",
        "parameters": {"type": "object", "properties": {"provider_id": {"type": "string"}},
                       "required": ["provider_id"]}}},
    {"type": "function", "function": {
        "name": "get_community_mentions",
        "description": "Sample community-group posts that mention one provider.",
        "parameters": {"type": "object", "properties": {"provider_id": {"type": "string"}},
                       "required": ["provider_id"]}}},
    {"type": "function", "function": {
        "name": "find_alternatives",
        "description": "Similar providers who ARE accepting new patients, for a provider who is full.",
        "parameters": {"type": "object", "properties": {
            "provider_id": {"type": "string"},
            "insurance": {"type": "string"},
            "max_miles": {"type": "number"}},
            "required": ["provider_id"]}}},
    {"type": "function", "function": {
        "name": "compare_providers",
        "description": ("After reading reviews for 2-3 providers, score them side by side. Scores are 1-5 "
                        "(5 is best) and must come only from the reviews; use 3 when the reviews do not say. "
                        "Each row needs one EXACT quote copied from that provider's reviews. Call once."),
        "parameters": {"type": "object", "properties": {
            "priority": {"type": "string", "description": "What matters most to the person, in a few words"},
            "rows": {"type": "array", "items": {"type": "object", "properties": {
                "provider_id": {"type": "string"},
                "rank": {"type": "integer", "description": "1 = best for this person"},
                "wait": {"type": "integer", "description": "1-5, 5 = short wait"},
                "phone": {"type": "integer", "description": "1-5, 5 = easy to reach"},
                "listening": {"type": "integer", "description": "1-5, 5 = listens well"},
                "quote": {"type": "string", "description": "exact words from one of this provider's reviews"},
                "why": {"type": "string", "description": "one short line"}},
                "required": ["provider_id", "rank", "wait", "phone", "listening", "quote", "why"]}}},
            "required": ["priority", "rows"]}}},
    {"type": "function", "function": {
        "name": "draft_contact",
        "description": "Write a draft call script, text, or email for one provider. Does not send anything.",
        "parameters": {"type": "object", "properties": {
            "provider_id": {"type": "string"},
            "channel": {"type": "string", "enum": ["call", "text", "email"]},
            "reason": {"type": "string"}},
            "required": ["provider_id"]}}},
]


def run_tool(name, args):
    """Run one tool safely. Bad input becomes an error the model can read and fix."""
    fn = T.TOOLS.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    try:
        result = fn(**args)
    except Exception as e:                      # let Muse see the problem and retry
        return {"error": f"{type(e).__name__}: {e}"}
    if isinstance(result, list):
        result = result[:8]                     # keep what Muse reads small
    return result


def handle_compare(args, texts_by_id, seen_ids):
    """The side-by-side tool. Like Meta's workshop 'record_fact': it REFUSES a row whose
    quote is not word for word in that provider's reviews, and tells Muse why.
    Returns (what Muse sees, the table for the screen or None)."""
    rows_in = args.get("rows")
    if not isinstance(rows_in, list) or not rows_in:
        return {"error": "rows is empty. Give 2-3 rows."}, None
    problems, rows = [], []
    for r in rows_in:
        r = r if isinstance(r, dict) else {}
        pid = str(r.get("provider_id", ""))
        p = T._get(pid)
        if not p or pid not in seen_ids:
            problems.append(f"{pid or '?'}: not a provider returned by a tool")
            continue
        if pid not in texts_by_id:
            problems.append(f"{pid}: call get_reviews for it first")
            continue
        try:
            scores = {k: int(r.get(k)) for k in ("wait", "phone", "listening", "rank")}
        except (TypeError, ValueError):
            problems.append(f"{pid}: wait, phone, listening and rank must be whole numbers")
            continue
        if not all(1 <= scores[k] <= 5 for k in ("wait", "phone", "listening")):
            problems.append(f"{pid}: scores must be 1 to 5")
            continue
        quote = str(r.get("quote", ""))
        if len(checks.normalize(quote)) < 8 or not checks.quote_in_sources(quote, texts_by_id[pid]):
            problems.append(f"{pid}: quote not found in its reviews. Copy exact words from get_reviews")
            continue
        rows.append({"id": pid, "name": p["name"], "city": p["city"],
                     "next": (p["next_available"] or [""])[0], "quote": quote.strip(),
                     "why": str(r.get("why", ""))[:160], **scores})
    if problems:
        return {"error": "; ".join(problems)}, None
    rows.sort(key=lambda x: x["rank"])
    table = {"priority": str(args.get("priority", ""))[:80], "rows": rows}
    return {"accepted": True, "count": len(rows)}, table


def friendly(name, args, result):
    """One plain line for the live panel and the 'how I found this' list."""
    def who():
        p = T._get(str(args.get("provider_id", "")))
        return p["name"] if p else "a provider"
    n = len(result) if isinstance(result, list) else None
    if isinstance(result, dict) and "error" in result:
        if name == "compare_providers":
            return "A quote did not match the reviews, so Muse is fixing it"
        return f"{name} had a problem, trying again"
    if name == "search_providers":
        what = " ".join(x for x in [args.get("specialty") or "providers",
                                    f"({args['focus']})" if args.get("focus") else ""] if x)
        where = f" near {args['city']}" if args.get("city") else ""
        plan = f", {args['insurance']}" if args.get("insurance") else ""
        miles = f", within {args['max_miles']} mi" if args.get("max_miles") else ""
        return f"Searching {what}{where}{plan}{miles} → {n} found"
    if name == "find_alternatives":
        return f"Looking for alternatives to {who()} → {n} found"
    if name == "check_availability":
        return f"Checking openings for {who()}"
    if name == "get_reviews":
        return f"Reading patient reviews for {who()}"
    if name == "get_community_mentions":
        return f"Reading community posts about {who()}"
    if name == "compare_providers":
        k = result.get("count", 0)
        return f"Scoring wait time, phone access and listening → {k} quote{'' if k == 1 else 's'} verified"
    if name == "draft_contact":
        return f"Drafting a {args.get('channel', 'call')} message for {who()}"
    return name


def describe(name, args, result):
    """A technical line for the saved run log."""
    shown = ", ".join(f"{k}={v}" for k, v in args.items() if v not in (None, "", False) and k != "rows")
    return f"{name}({shown})"


def card(p_short):
    """Full details for a result card on screen."""
    p = T._get(p_short["id"])
    return {"id": p["id"], "name": p["name"], "specialty": p["specialty"], "focus": p["focus"],
            "city": p["city"], "miles_away": p_short.get("miles_away"), "gender": p["gender"],
            "next_available": p["next_available"], "accepting_new": p["accepting_new"],
            "insurance": p["insurance"], "languages": p["languages"],
            "telehealth": p["telehealth"], "treats_kids": p["treats_kids"], "phone": p["phone"]}


def _call_model(client, kwargs):
    """Call Muse. If the API rejects reasoning_effort, try once without it."""
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as e:
        if "reasoning" in str(e).lower() and "reasoning_effort" in kwargs:
            kwargs.pop("reasoning_effort")
            os.environ["REASONING_EFFORT"] = ""      # remember: don't send it again
            return client.chat.completions.create(**kwargs)
        raise


def ask(history, user_text, on_step=None):
    """Run the agent for one user message. `history` is a list kept per visitor.
    on_step(text) is called as each step happens, for the live panel."""
    def emit(text):
        if on_step:
            on_step(text)

    client = get_client()
    messages = [{"role": "developer", "content": SYSTEM.format(today=date.today().isoformat())}]
    messages += history
    messages.append({"role": "user", "content": user_text})
    steps, candidates, comparison = [], [], None
    seen_names, seen_ids = set(), set()              # what the tools really returned
    seen_texts, texts_by_id = [], {}
    retried = False
    verified, quotes_checked = None, 0
    log = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "user": user_text, "turns": []}
    answer = ""

    # The agent loop: ask Muse, run the tools it picks, repeat until it gives a final answer.
    # MAX_TURNS stops it from looping forever.
    for turn in range(MAX_TURNS):
        if turn == MAX_TURNS - 1:
            messages.append({"role": "developer", "content": "Last step. Give your final answer now, using what you have."})
        kwargs = dict(model=MODEL, messages=messages, tools=TOOL_DEFS, max_completion_tokens=1500)
        effort = os.getenv("REASONING_EFFORT", "low")
        if effort:
            kwargs["reasoning_effort"] = effort
        try:
            resp = _call_model(client, kwargs)
        except Exception as e:
            log["error"] = str(e)
            _save(log)
            return {"answer": "Sorry, I couldn't reach the model just now. Please try again.",
                    "steps": steps, "candidates": candidates, "error": str(e)}
        msg = resp.choices[0].message
        calls = getattr(msg, "tool_calls", None) or []

        if not calls:                            # Muse wrote a final answer
            answer = (msg.content or "").strip()
            bad_names = checks.unknown_names(answer, seen_names)
            quotes = checks.extract_quotes(answer)
            bad_quotes = [q for q in quotes if not checks.quote_in_sources(q, seen_texts)]
            quotes_checked += len(quotes) - len(bad_quotes)
            log["turns"].append({"final": answer, "unknown_names": bad_names, "bad_quotes": bad_quotes})
            if (bad_names or bad_quotes) and not retried:     # one correction round
                retried = True
                emit("A check failed, so Muse is rewriting its answer")
                problems = []
                if bad_names:
                    problems.append(f"{', '.join(bad_names)} did not come from a tool")
                if bad_quotes:
                    problems.append("these quotes did not match any review a tool returned: "
                                    + "; ".join(bad_quotes))
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "developer", "content":
                                 "Your answer had problems: " + ". ".join(problems) +
                                 ". Rewrite it using only doctors the tools returned, and quote "
                                 "reviews word for word (or leave the quote out)."})
                continue
            verified = not (bad_names or bad_quotes)
            if not verified:
                answer += "\n\n(Note: some details could not be verified. Please double-check.)"
            break

        # Muse asked for tools: keep its message, then run each tool
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in calls]})
        for c in calls:
            name = c.function.name
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if name == "compare_providers":
                result, table = handle_compare(args, texts_by_id, seen_ids)
                if table:
                    comparison = table
                    quotes_checked += len(table["rows"])
            else:
                result = run_tool(name, args)
            line = friendly(name, args, result)
            steps.append(line)
            emit(line)
            log["turns"].append({"tool": name, "args": args, "result": describe(name, args, result)})
            if isinstance(result, list):
                for r in result:
                    seen_names.add(r["name"])
                    seen_ids.add(r["id"])
                if name in ("search_providers", "find_alternatives") and result:
                    candidates = [card(r) for r in result[:5]]
            elif isinstance(result, dict):
                if result.get("name"):
                    seen_names.add(result["name"])
                if result.get("to"):
                    seen_names.add(result["to"])
                if result.get("id"):
                    seen_ids.add(result["id"])
                texts = [t for t in result.get("reviews", []) if isinstance(t, str)]
                texts += [p.get("text", "") for p in result.get("posts", []) if isinstance(p, dict)]
                if texts and result.get("id"):
                    texts_by_id.setdefault(result["id"], []).extend(texts)
                    seen_texts += texts
            messages.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result)})
    else:
        answer = "I ran out of steps. Try a simpler request, like a doctor type and a city."

    # Show the compared doctors first on screen
    if comparison:
        order = {r["id"]: r["rank"] for r in comparison["rows"]}
        have = {c["id"] for c in candidates}
        candidates += [card({"id": pid}) for pid in order if pid not in have]
        candidates.sort(key=lambda c: order.get(c["id"], 99))
        candidates = candidates[:5]

    # Remember only the plain conversation so follow-up questions work
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": answer})
    del history[:-12]
    log["answer"] = answer
    log["verified"] = verified
    _save(log)
    return {"answer": answer, "steps": steps, "candidates": candidates, "comparison": comparison,
            "checks": {"verified": verified, "quotes_matched": quotes_checked}}


def _save(log):
    """Save a record of every run, so we can show and debug what the agent did."""
    try:
        os.makedirs(RUN_LOG_DIR, exist_ok=True)
        name = time.strftime("%Y%m%d-%H%M%S") + ".json"
        with open(os.path.join(RUN_LOG_DIR, name), "w", encoding="utf-8") as f:
            json.dump(log, f, indent=1)
    except OSError:
        pass
