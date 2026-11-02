"""A fake model, ONLY for testing the agent loop without an API key.
It is NOT Muse. It follows a fixed script. Use it with:  MOCK_MODEL=1
"""
import json
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
        if len(tool_msgs) == 1:                              # step 2: look at the first result
            found = json.loads(tool_msgs[0]["content"])
            if found:
                return _reply(calls=[_call(2, "get_community_mentions", {"provider_id": found[0]["id"]}),
                                     _call(3, "check_availability", {"provider_id": found[0]["id"]})])
            return _reply("I couldn't find a match. Try a wider distance or another plan.")
        found = json.loads(tool_msgs[0]["content"])           # step 3: write the answer
        top = found[0]
        more = f" Next is {found[1]['name']} in {found[1]['city']}." if len(found) > 1 else ""
        return _reply(f"[MOCK ANSWER] Top pick: {top['name']} in {top['city']}, "
                      f"opens {top['next_available'][0]}. Focus: {', '.join(top['focus'])}.{more}")


class MockClient:
    def __init__(self):
        self.chat = NS(completions=_Completions())
