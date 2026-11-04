"""Tests for tools.py: the plain-code search tools. No AI involved, so results must be exact.
Run all tests with:  python -m pytest -q"""
from datetime import date

import tools as T


def test_search_respects_every_filter():
    res = T.search_providers("Pediatrics", city="Issaquah", insurance="Premera", gender="female", max_miles=15)
    assert res, "sample data should have at least one match"
    for r in res:
        p = T._get(r["id"])
        assert p["specialty"] == "Pediatrics" and p["gender"] == "female"
        assert "Premera" in p["insurance"] and p["accepting_new"]
        assert r["miles_away"] <= 15


def test_results_sorted_by_soonest_opening():
    res = T.search_providers("Pediatrics", city="Seattle", max_miles=30)
    firsts = [r["next_available"][0] for r in res]
    assert firsts == sorted(firsts)


def test_focus_filter_finds_sub_specialty():
    for r in T.search_providers(focus="sinus"):
        assert any("sinus" in f.lower() for f in r["focus"])
    assert T.search_providers(focus="pcos", city="Seattle", max_miles=15)


def test_nothing_matches_gives_empty_list_not_crash():
    assert T.search_providers("Pediatrics", insurance="Not A Real Plan") == []
    assert T.search_providers(specialty="Astrology") == []


def test_accepting_new_default_and_override():
    assert all(r["accepting_new"] for r in T.search_providers())
    assert any(not r["accepting_new"] for r in T.search_providers(accepting_new=False))


def test_kids_telehealth_language_filters():
    assert all(T._get(r["id"])["treats_kids"] for r in T.search_providers(kids=True))
    assert all(T._get(r["id"])["telehealth"] for r in T.search_providers(telehealth=True))
    for r in T.search_providers(language="Spanish"):
        assert "spanish" in [l.lower() for l in T._get(r["id"])["languages"]]


def test_distance_is_symmetric_and_zero_for_same_city():
    assert T._miles("Seattle", "Seattle") == 0
    assert T._miles("Seattle", "Bellevue") == T._miles("Bellevue", "Seattle")
    assert T._miles("Seattle", "Atlantis") is None


def test_unknown_city_does_not_filter_everything_out():
    assert T.search_providers("Pediatrics", city="Atlantis", max_miles=5)


def test_alternatives_never_include_the_same_doctor_and_are_accepting():
    full = next(p for p in T.PROVIDERS if not p["accepting_new"])
    alts = T.find_alternatives(full["id"], city=full["city"])
    assert all(a["id"] != full["id"] and a["accepting_new"] for a in alts)
    assert all(a["specialty"] == full["specialty"] for a in alts)


def test_alternatives_never_list_a_doctor_who_is_accepting_as_their_own_alternative():
    p = next(p for p in T.PROVIDERS if p["accepting_new"])
    assert p["id"] not in [a["id"] for a in T.find_alternatives(p["id"], city=p["city"])]


def test_alternatives_measure_from_the_persons_city():
    full = next(p for p in T.PROVIDERS if not p["accepting_new"] and p["city"] != "Bellevue")
    for a in T.find_alternatives(full["id"], city="Bellevue", max_miles=10):
        assert a["miles_away"] == T._miles("Bellevue", a["city"]) <= 10


def test_availability_before_date_filter():
    p = T.PROVIDERS[0]
    cutoff = p["next_available"][0]
    got = T.check_availability(p["id"], before_date=cutoff)["dates"]
    assert got and all(d <= cutoff for d in got)
    assert T.check_availability(p["id"], before_date="2000-01-01")["dates"] == []


def test_unknown_provider_ids_return_errors():
    for fn in (T.check_availability, T.get_reviews, T.get_community_mentions, T.find_alternatives, T.draft_contact):
        assert "error" in fn("p999")


def test_reviews_and_mentions_come_straight_from_the_data():
    p = T.PROVIDERS[0]
    assert T.get_reviews(p["id"])["reviews"] == p["reviews"]
    assert T.get_community_mentions(p["id"])["posts"] == p["community_posts"]


def test_draft_contact_all_channels_and_never_sends():
    p = T.PROVIDERS[0]
    call = T.draft_contact(p["id"], "call", "a visit for my son")
    assert p["phone"] in call["draft"] and "a visit for my son" in call["draft"]
    email = T.draft_contact(p["id"], "email")
    assert email["draft"].startswith("Subject:") and p["name"] in email["draft"]
    text = T.draft_contact(p["id"], "text")
    assert p["name"] in text["draft"]
    assert "Nothing was sent" in call["note"]


def test_tools_table_matches_what_the_agent_offers():
    import agent
    offered = {d["function"]["name"] for d in agent.TOOL_DEFS} - {"compare_providers"}
    assert offered == set(T.TOOLS)


def test_sample_dates_are_never_in_the_past():
    today = date.today().isoformat()
    for p in T.PROVIDERS:
        assert all(d >= today for d in p["next_available"]), p["id"]


def test_small_city_typos_still_work():
    assert T._city("Lynwood") == "lynnwood" and T._city("  BELLEVUE ") == "bellevue" and T._city("Issaqua") == "issaquah"
    assert T._miles("Lynwood", "Lynnwood") == 0
    assert T._city("Atlantis") is None and T._city("") is None and T._city(None) is None
    near = T.search_providers("Pediatrics", city="Lynwood", max_miles=3)
    assert near and all(r["miles_away"] <= 3 for r in near)
