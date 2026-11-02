"""A fake model, ONLY for testing the agent loop without an API key.
It is NOT Muse. It follows a fixed script. Use it with:  MOCK_MODEL=1
  MOCK_BAD_QUOTE=1  -> first comparison uses a fake quote (the tool must refuse it)
  MOCK_BAD_FINAL=1  -> first final answer names a fake doctor (the check must catch it)
"""
import json
import os
import re
from types import SimpleNamespace as NS

import tools as T

FOCUS = ["adenoids", "sinus", "pcos", "asthma", "adhd", "eczema", "migraines", "knee"]
SPECS = {"pediatric": "Pediatrics", "primary care": "Primary Care", "ent": "ENT"}


def _call(i, name, args):
    return NS(id=f"call_{i}", type="function",
              function=NS(name=name, arguments=json.dumps(args)))


def _reply(content=None, calls=None):
    msg = NS(content=content, tool_calls=calls or None)
    return NS(choices=[NS(message=msg, finish_reason="tool_calls" if calls else "stop")])


class _Completions:
    def create(self, model, messages, tools=None, **kw):
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        text = messages[last_user]["content"].lower()
        tool_msgs = [m for m in messages[last_user:] if m["role"] == "tool"]
        if not tool_msgs:                                    # step 1: search
            args = {}
            for c in T.CITIES:
                if c in text:
                    args["city"] = c.title()
            for plan in ["aetna ppo", "premera", "cigna", "regence", "unitedhealthcare", "apple health"]:
                if plan in text:
                    args["insurance"] = plan.title() if plan != "aetna ppo" else "Aetna PPO"
            for f in FOCUS:
                if f in text:
                    args["focus"] = f
            for k, v in SPECS.items():
                if re.search(r"\b" + k, text):
                    args["specialty"] = v
            if "pediatric" in text:
                args["kids"] = True
            if "female" in text:
                args["gender"] = "female"
            args["max_miles"] = 20
            return _reply(calls=[_call(1, "search_providers", args)])
        found = json.loads(tool_msgs[0]["content"])
        if not found:
            return _reply("I couldn't find a match. Try a wider distance or another plan.")
        top = found[:2]
        n = len(top)
        if len(tool_msgs) == 1:                              # step 2: read reviews for the top 2
            return _reply(calls=[_call(10 + i, "get_reviews", {"provider_id": p["id"]}) for i, p in enumerate(top)])
        reviews = {p["id"]: json.loads(tool_msgs[1 + i]["content"])["reviews"] for i, p in enumerate(top)}

        def compare(bad):
            rows = [{"provider_id": p["id"], "rank": i + 1, "wait": 4 - i, "phone": 3 + i, "listening": 5 - i,
                     "quote": ("the best doctor in the whole world" if bad and i == 0 else reviews[p["id"]][0]),
                     "why": "Opens soonest" if i == 0 else "Close by"} for i, p in enumerate(top)]
            return _reply(calls=[_call(20, "compare_providers", {"priority": "soonest opening", "rows": rows})])

        if len(tool_msgs) == 1 + n:                          # step 3: compare
            return compare(bad=os.getenv("MOCK_BAD_QUOTE") == "1")
        if '"error"' in tool_msgs[-1]["content"]:            # tool refused: fix and retry
            return compare(bad=False)
        corrected = any("had problems" in str(m.get("content", "")) for m in messages)
        if os.getenv("MOCK_BAD_FINAL") == "1" and not corrected:
            return _reply("[MOCK] Top pick: Dr. Zed Madeup.")
        return _reply(f"[MOCK ANSWER] Top pick: {top[0]['name']} in {top[0]['city']}. "
                      f'Patients say "{reviews[top[0]["id"]][0]}"')


class MockClient:
    def __init__(self):
        self.chat = NS(completions=_Completions())
