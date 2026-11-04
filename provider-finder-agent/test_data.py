"""Tests for the sample data. A bad row here would make the app say something wrong."""
import csv
import json
import os
import re

import tools as T

HERE = os.path.dirname(os.path.abspath(__file__))
FIELDS = {"id", "name", "gender", "specialty", "focus", "treats_kids", "city", "phone", "telehealth",
          "languages", "insurance", "accepting_new", "next_available", "reviews", "community_posts"}
BANNED = ("member", "ssn", "dob", "birth", "address_line", "email")


def test_every_row_has_the_same_fields_and_nothing_private():
    for p in T.PROVIDERS:
        assert set(p) == FIELDS, p["id"]
        assert not [k for k in p if any(b in k.lower() for b in BANNED)]


def test_ids_and_names_are_unique():
    ids = [p["id"] for p in T.PROVIDERS]
    names = [p["name"] for p in T.PROVIDERS]
    assert len(set(ids)) == len(ids) and len(set(names)) == len(names)
    assert all(n.startswith("Dr. ") for n in names)


def test_values_make_sense():
    for p in T.PROVIDERS:
        assert p["gender"] in ("female", "male")
        assert p["city"].lower() in T.CITIES, p["id"]
        assert re.fullmatch(r"\(\d{3}\) 555-\d{4}", p["phone"]), p["phone"]      # 555 = clearly fake
        assert p["focus"] and p["insurance"] and p["languages"] and p["next_available"]
        assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in p["next_available"])
        assert p["next_available"] == sorted(p["next_available"])
        assert isinstance(p["accepting_new"], bool) and isinstance(p["telehealth"], bool)


def test_reviews_exist_and_are_plain_text():
    for p in T.PROVIDERS:
        assert len(p["reviews"]) >= 2, p["id"]
        assert all(isinstance(r, str) and len(r.split()) >= 2 for r in p["reviews"]), p["id"]
        for post in p["community_posts"]:
            assert post["source"] and len(post["text"].split()) >= 5


def test_no_real_facebook_content_is_claimed():
    for p in T.PROVIDERS:
        for post in p["community_posts"]:
            assert "facebook.com" not in json.dumps(post).lower()


def test_enough_variety_for_the_demo():
    assert len(T.PROVIDERS) >= 100
    assert len({p["specialty"] for p in T.PROVIDERS}) >= 10
    assert len({i for p in T.PROVIDERS for i in p["insurance"]}) >= 5
    assert any(not p["accepting_new"] for p in T.PROVIDERS)


def test_csv_copy_matches_json():
    with open(os.path.join(HERE, "providers.csv"), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(json.load(open(os.path.join(HERE, "providers.json"))))
