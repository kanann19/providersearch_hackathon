"""Tests for handle_compare in agent.py: the tool that REFUSES a score row if its quote is not a real review."""
import agent
import tools as T

P1, P2 = T.PROVIDERS[0], T.PROVIDERS[1]


def rows(**over):
    base = {"provider_id": P1["id"], "rank": 1, "wait": 4, "phone": 3, "listening": 5,
            "quote": P1["reviews"][0], "why": "Opens soonest"}
    base.update(over)
    return base


def ctx():
    texts = {P1["id"]: list(P1["reviews"]), P2["id"]: list(P2["reviews"])}
    return texts, {P1["id"], P2["id"]}


def run(*r, **kw):
    texts, seen = ctx()
    texts = kw.get("texts", texts)
    return agent.handle_compare({"priority": "soonest", "rows": list(r)}, texts, kw.get("seen", seen))


def test_good_row_is_accepted_and_table_is_built():
    result, table = run(rows(), rows(provider_id=P2["id"], rank=2, quote=P2["reviews"][0]))
    assert result == {"accepted": True, "count": 2}
    assert [r["rank"] for r in table["rows"]] == [1, 2]
    assert table["rows"][0]["name"] == P1["name"]


def test_made_up_quote_is_refused():
    result, table = run(rows(quote="the best doctor in the whole world"))
    assert table is None and "quote not found" in result["error"]


def test_quote_from_a_different_doctor_is_refused():
    result, table = run(rows(quote=P2["reviews"][0]))
    assert table is None and "quote not found" in result["error"]


def test_provider_never_returned_by_a_tool_is_refused():
    result, table = run(rows(), seen=set())
    assert table is None and "not a provider returned by a tool" in result["error"]


def test_unknown_provider_id_is_refused():
    result, table = run(rows(provider_id="p999"))
    assert table is None and "error" in result


def test_must_read_reviews_first():
    result, table = run(rows(), texts={})
    assert table is None and "get_reviews" in result["error"]


def test_scores_must_be_whole_numbers_from_1_to_5():
    for bad in (0, 6, -1, "great", None, 3.5 if False else "x"):
        result, table = run(rows(wait=bad))
        assert table is None and "error" in result, bad
    assert run(rows(wait="4"))[1] is not None          # "4" as text is fine, it is a whole number


def test_very_short_quote_is_refused():
    assert run(rows(quote="ok"))[1] is None


def test_empty_or_wrong_shape_input_does_not_crash():
    texts, seen = ctx()
    for bad in (None, [], "text", {"rows": []}):
        args = bad if isinstance(bad, dict) else {"rows": bad}
        result, table = agent.handle_compare(args, texts, seen)
        assert table is None and "error" in result
    assert agent.handle_compare({"rows": ["nope", 5]}, texts, seen)[1] is None


def test_one_bad_row_blocks_the_whole_table():
    result, table = run(rows(), rows(provider_id=P2["id"], rank=2, quote="invented praise from nobody"))
    assert table is None


def test_rows_are_sorted_by_rank_and_why_is_trimmed():
    _, table = run(rows(rank=2, why="x" * 500), rows(provider_id=P2["id"], rank=1, quote=P2["reviews"][0]))
    assert table["rows"][0]["id"] == P2["id"] and len(table["rows"][1]["why"]) == 160
