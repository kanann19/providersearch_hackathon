"""tools.py: the six jobs the agent can ask for, in plain words.

Muse decides WHICH tool to use. These functions just do the exact work:
search the list, check dates, read reviews, find alternatives, write a draft message.
All the data comes from providers.json and is SAMPLE data (made up).
No AI is in this file, so the results are always exact.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "providers.json")) as f:
    PROVIDERS = json.load(f)

# Sample appointment dates were made on 2026-10-26. Slide them forward so
# they are always in the future, no matter what day you run the demo.
from datetime import date, timedelta
_DAYS_LATE = max(0, (date.today() - date(2026, 10, 26)).days)
if _DAYS_LATE:
    for _p in PROVIDERS:
        _p["next_available"] = [
            (date.fromisoformat(d) + timedelta(days=_DAYS_LATE)).isoformat()
            for d in _p["next_available"]
        ]

# Rough city centers (lat, lon) so we can measure distance
CITIES = {
    "seattle": (47.61, -122.33),
    "bellevue": (47.61, -122.20),
    "kirkland": (47.68, -122.21),
    "redmond": (47.67, -122.12),
    "issaquah": (47.53, -122.03),
    "lynnwood": (47.82, -122.31),
    "renton": (47.48, -122.22),
    "everett": (47.98, -122.20),
    "bothell": (47.76, -122.21),
    "mercer island": (47.57, -122.22),
    "shoreline": (47.76, -122.34),
    "kent": (47.38, -122.23),
}


def _miles(city_a, city_b):
    a, b = CITIES.get(city_a.lower()), CITIES.get(city_b.lower())
    if not a or not b:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return round(3959 * 2 * math.asin(math.sqrt(h)), 1)


def _get(provider_id):
    for p in PROVIDERS:
        if p["id"] == provider_id:
            return p
    return None


def _short(p, from_city=None):
    """Small summary the agent sees for each provider."""
    return {
        "id": p["id"], "name": p["name"], "gender": p["gender"],
        "specialty": p["specialty"], "focus": p["focus"], "city": p["city"],
        "miles_away": _miles(from_city, p["city"]) if from_city else None,
        "accepting_new": p["accepting_new"],
        "next_available": p["next_available"][:1],
        "telehealth": p["telehealth"], "languages": p["languages"],
    }


def search_providers(specialty=None, city=None, insurance=None, gender=None,
                     max_miles=None, kids=None, telehealth=None, language=None,
                     accepting_new=True, focus=None):
    """Find providers that match. Any filter left empty is ignored.
    focus = a sub-specialty, like "sinus problems" or "PCOS"."""
    results = []
    for p in PROVIDERS:
        if specialty and specialty.lower() != p["specialty"].lower():
            continue
        if focus and not any(focus.lower() in f.lower() for f in p["focus"]):
            continue
        if insurance and insurance.lower() not in [i.lower() for i in p["insurance"]]:
            continue
        if gender and gender.lower() != p["gender"]:
            continue
        if kids and not p["treats_kids"]:
            continue
        if telehealth and not p["telehealth"]:
            continue
        if language and language.lower() not in [l.lower() for l in p["languages"]]:
            continue
        if accepting_new and not p["accepting_new"]:
            continue
        miles = _miles(city, p["city"]) if city else None
        if max_miles is not None and miles is not None and miles > max_miles:
            continue
        results.append(_short(p, city))
    results.sort(key=lambda r: (r["next_available"] or ["9999"])[0])
    return results


def check_availability(provider_id, before_date=None):
    """Next open appointment dates (optionally only before a date, YYYY-MM-DD)."""
    p = _get(provider_id)
    if not p:
        return {"error": "provider not found"}
    dates = [d for d in p["next_available"] if not before_date or d <= before_date]
    return {"id": provider_id, "name": p["name"], "accepting_new": p["accepting_new"],
            "dates": dates, "note": "Sample dates. Real doctors rarely publish these."}


def get_reviews(provider_id):
    """Raw reviews. Muse reads these and turns them into scores."""
    p = _get(provider_id)
    return {"id": provider_id, "name": p["name"], "reviews": p["reviews"]} if p else {"error": "not found"}


def get_community_mentions(provider_id):
    """Sample posts from parent/community groups that mention this provider."""
    p = _get(provider_id)
    if not p:
        return {"error": "not found"}
    return {"id": provider_id, "name": p["name"], "posts": p["community_posts"],
            "note": "Sample posts, not real Facebook data."}


def find_alternatives(provider_id, insurance=None, max_miles=25):
    """If a provider is not taking new patients, suggest similar ones who are."""
    p = _get(provider_id)
    if not p:
        return {"error": "not found"}
    return search_providers(specialty=p["specialty"], city=p["city"], insurance=insurance,
                            max_miles=max_miles, kids=p["treats_kids"] or None)


def draft_contact(provider_id, channel="call", reason="a new patient appointment"):
    """Writes a message or call script. It does NOT send anything."""
    p = _get(provider_id)
    if not p:
        return {"error": "not found"}
    if channel == "call":
        text = (f"Call {p['phone']}. Say: 'Hi, I'm looking for {reason} with {p['name']}. "
                f"Are you accepting new patients? What is your next opening? Do you take my plan?'")
    elif channel == "email":
        text = (f"Subject: New patient request\n\nHello, I would like {reason} with {p['name']}. "
                f"Are you taking new patients, and what is the earliest opening? Thank you.")
    else:
        text = f"Hi, I'd like {reason} with {p['name']}. Are you taking new patients? Earliest opening?"
    return {"channel": channel, "to": p["name"], "phone": p["phone"], "draft": text,
            "note": "Draft only. Nothing was sent."}


# Lookup table: tool name -> function. agent.py uses it to run whichever tool Muse picks.
TOOLS = {
    "search_providers": search_providers,
    "check_availability": check_availability,
    "get_reviews": get_reviews,
    "get_community_mentions": get_community_mentions,
    "find_alternatives": find_alternatives,
    "draft_contact": draft_contact,
}
