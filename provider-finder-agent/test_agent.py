"""Tests for the agent loop in agent.py, using a fake model.
We make the fake model misbehave on purpose and check that OUR CODE catches it."""
import json
import os

import pytest

import agent
import tools as T
from conftest import call, reply

ASK = "Female pediatrician near Issaquah, Premera"


def run(text=ASK, history=None, on_step=None):
    return agent.ask(history if history is not None else [], text, on_step=on_step)


# ---------- the happy path (offline mock model) ----------
def test_full_run_gives_answer_cards_table_and_checks():
    r = run()
    assert r["answer"].startswith("[MOCK ANSWER]")
    assert r["candidates"] and r["comparison"]["rows"]
    assert r["checks"] == {"verified": True, "quotes_matched": r["checks"]["quotes_matched"]}
    assert r["checks"]["quotes_matched"] >= 2


def test_cards_are_real_providers_that_match_the_request():
    for c in run()["candidates"]:
        p = T._get(c["id"])
        assert p and p["gender"] == "female" and "Premera" in p["insurance"] and p["accepting_new"]


def test_top_cards_carry_checked_why_and_quote():
    r = run()
    by_id = {x["id"]: x for x in r["comparison"]["rows"]}
    for c in r["candidates"]:
        if c["id"] in by_id:
            assert c["why"] == by_id[c["id"]]["why"]
            assert c["quote"] in " ".join(T._get(c["id"])["reviews"])      # word for word


def test_steps_stream_live_and_match_saved_steps():
    seen = []
    r = run(on_step=seen.append)
    assert seen == r["steps"] and any("Searching" in s for s in seen)


def test_follow_up_history_is_kept_and_trimmed():
    h = []
    for _ in range(10):
        run(history=h)
    assert len(h) == 12 and h[-2]["role"] == "user" and h[-1]["role"] == "assistant"


def test_every_run_is_saved_to_a_log():
    run()
    files = os.listdir(agent.RUN_LOG_DIR)
    assert len(files) == 1
    log = json.load(open(os.path.join(agent.RUN_LOG_DIR, files[0])))
    assert log["user"] == ASK and log["verified"] is True and log["turns"]


def test_no_match_shows_no_cards(scripted):
    scripted([reply(calls=[call(1, "search_providers", {"specialty": "Astrology"})]),
              reply("I couldn't find a match. Try a wider distance.")])
    r = run()
    assert r["candidates"] == [] and r["comparison"] is None and r["checks"]["verified"] is True


# ---------- Muse misbehaves: our checks must catch it ----------
def test_fake_quote_in_comparison_is_refused_then_fixed(monkeypatch):
    monkeypatch.setenv("MOCK_BAD_QUOTE", "1")
    seen = []
    r = run(on_step=seen.append)
    assert any("did not match" in s for s in seen)           # the refusal was shown
    assert r["comparison"] and r["checks"]["verified"] is True
    texts = " ".join(" ".join(T._get(x["id"])["reviews"]) for x in r["comparison"]["rows"])
    assert all(x["quote"] in texts for x in r["comparison"]["rows"])


def test_made_up_doctor_in_final_answer_triggers_a_rewrite(monkeypatch):
    monkeypatch.setenv("MOCK_BAD_FINAL", "1")
    seen = []
    r = run(on_step=seen.append)
    assert "Zed Madeup" not in r["answer"] and r["checks"]["verified"] is True
    assert any("check failed" in s for s in seen)


def test_if_the_rewrite_is_still_wrong_the_answer_is_marked_unverified(scripted):
    scripted([reply("Dr. Nobody Real is great."), reply("Still Dr. Nobody Real.")])
    r = run()
    assert r["checks"]["verified"] is False and "could not be verified" in r["answer"]


def test_made_up_quote_in_final_answer_is_caught(scripted):
    scripted([reply('Patients say "this doctor cured everything instantly".'), reply("Plain answer, no quote.")])
    r = run()
    assert r["checks"]["verified"] is True and "cured" not in r["answer"]


def test_quote_copied_from_a_tool_result_passes(scripted):
    p = next(p for p in T.PROVIDERS if any(len(r.split()) >= 3 for r in p["reviews"]))
    quote = next(r for r in p["reviews"] if len(r.split()) >= 3).rstrip(".!")
    scripted([reply(calls=[call(1, "get_reviews", {"provider_id": p["id"]})]),
              reply(f'{p["name"]} - patients say "{quote}".')])
    r = run()
    assert r["checks"] == {"verified": True, "quotes_matched": 1}


def test_empty_replies_are_retried_then_used(scripted):
    c = scripted([reply(""), reply(None), reply("Here you go.")])
    assert run()["answer"] == "Here you go." and len(c.seen) == 3


def test_model_error_gives_friendly_message_and_logs(scripted):
    scripted([RuntimeError("network down")])
    r = run()
    assert "couldn't reach the model" in r["answer"] and "network down" in r["error"]


def test_loop_stops_at_max_turns(scripted):
    p = T.PROVIDERS[0]["id"]
    c = scripted([reply(calls=[call(i, "check_availability", {"provider_id": p})]) for i in range(agent.MAX_TURNS)])
    r = run()
    assert len(c.seen) == agent.MAX_TURNS and "ran out of steps" in r["answer"]


def test_last_turn_tells_the_model_to_finish(scripted):
    p = T.PROVIDERS[0]["id"]
    c = scripted([reply(calls=[call(i, "check_availability", {"provider_id": p})]) for i in range(agent.MAX_TURNS)])
    run()
    assert "Last step" in json.dumps(c.seen[-1]["messages"])


# ---------- tool safety ----------
def test_unknown_tool_and_bad_arguments_become_errors_not_crashes():
    assert "unknown tool" in agent.run_tool("rm_rf", {})["error"]
    assert "error" in agent.run_tool("search_providers", {"nonsense": 1})
    assert "error" in agent.run_tool("check_availability", {})


def test_garbled_tool_arguments_do_not_crash_the_loop(scripted):
    bad = call(1, "search_providers", {})
    bad.function.arguments = "{not json"
    scripted([reply(calls=[bad]), reply("Done.")])
    assert run()["answer"] == "Done."


def test_big_results_are_trimmed_for_the_model():
    assert len(agent.run_tool("search_providers", {})) <= 8


def test_tool_messages_follow_the_api_rules(scripted):
    p = T.PROVIDERS[0]["id"]
    c = scripted([reply(calls=[call(1, "check_availability", {"provider_id": p}),
                               call(2, "get_reviews", {"provider_id": p})]), reply("ok")])
    run()
    msgs = c.seen[-1]["messages"]
    asst = next(m for m in msgs if m["role"] == "assistant")
    tool_ids = [m["tool_call_id"] for m in msgs if m["role"] == "tool"]
    assert [t["id"] for t in asst["tool_calls"]] == tool_ids == ["c1", "c2"]      # all calls answered, in order
    assert all(isinstance(t["function"]["arguments"], str) for t in asst["tool_calls"])


def test_tool_definitions_are_valid_and_complete():
    names = []
    for d in agent.TOOL_DEFS:
        assert d["type"] == "function"
        f = d["function"]
        assert f["name"] and f["description"] and f["parameters"]["type"] == "object"
        for req in f["parameters"].get("required", []):
            assert req in f["parameters"]["properties"]
        names.append(f["name"])
    assert len(set(names)) == len(names)


def test_system_prompt_keeps_the_safety_rules():
    s = agent.SYSTEM.format(today="2026-11-03")
    for must in ("NEVER diagnose", "Never ask for a member ID", "911", "word for word", "2026-11-03"):
        assert must in s


def test_no_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("MOCK_MODEL")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MODEL_API_KEY"):
        agent.get_client()


def test_chosen_language_is_added_to_the_instructions(scripted):
    c = scripted([reply("ok")])
    agent.ask([], "hello", language="Telugu")
    system = c.seen[0]["messages"][0]["content"]
    assert "chose Telugu" in system and "exactly as the tools gave them" in system


def test_english_or_no_language_adds_nothing(scripted):
    c = scripted([reply("ok"), reply("ok")])
    agent.ask([], "hello", language="English")
    agent.ask([], "hello")
    assert all("The person chose" not in k["messages"][0]["content"] for k in c.seen)
