"""Tests for extras.py: the insurance card reader (privacy matters here) and the voice settings."""
import json

import extras

PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def test_plan_matching_from_card_words():
    cases = {"Premera Blue Cross": "Premera", "REGENCE BlueShield": "Regence", "Cigna HealthCare": "Cigna",
             "Aetna Choice POS II": "Aetna PPO", "UnitedHealthcare Choice Plus": "UnitedHealthcare",
             "United Healthcare": "UnitedHealthcare", "Washington Apple Health": "Apple Health"}
    for said, plan in cases.items():
        assert extras.match_plan(said) == plan, said


def test_unclear_or_unknown_cards_give_no_plan():
    for said in ("UNKNOWN", "", None, "Some Local Co-op", "Premera and Regence"):
        assert extras.match_plan(said) is None, said


def test_every_matchable_plan_exists_in_the_provider_data():
    assert set(extras.PLAN_WORDS) <= extras.known_plans()


def test_card_result_contains_only_the_plan_never_numbers_or_names(monkeypatch):
    monkeypatch.setenv("MOCK_CARD_TEXT", "Premera Blue Cross  Member ID: XJK123456789  Jane Doe  Group 998877")
    r = extras.read_card(PNG)
    assert r["plan"] == "Premera"
    blob = json.dumps(r)
    assert "XJK" not in blob and "Jane" not in blob and "998877" not in blob


def test_unreadable_card_asks_the_person_to_type(monkeypatch):
    monkeypatch.setenv("MOCK_CARD_TEXT", "UNKNOWN")
    r = extras.read_card(PNG)
    assert r["plan"] is None and "type your plan" in r["message"]


def test_bad_uploads_are_rejected_before_any_model_call():
    assert extras.read_card("hello")["plan"] is None
    assert extras.read_card("data:text/html;base64,PHNjcmlwdD4=")["plan"] is None
    assert extras.read_card("data:image/png;base64," + "A" * (extras.MAX_IMAGE_CHARS + 1))["plan"] is None
    assert extras.read_card(None)["plan"] is None
    assert extras.read_card({"x": 1})["plan"] is None


def test_card_prompt_forbids_reading_numbers():
    assert "Do NOT read" in extras.CARD_PROMPT


def test_card_request_to_the_model_has_image_and_prompt(monkeypatch):
    """The real (non-mock) path: check the message we would send to Muse Spark."""
    import agent
    from conftest import Scripted, reply
    monkeypatch.delenv("MOCK_MODEL")
    c = Scripted([reply("Cigna")])
    monkeypatch.setattr(agent, "get_client", lambda: c)
    assert extras.read_card(PNG)["plan"] == "Cigna"
    parts = c.seen[0]["messages"][0]["content"]
    assert parts[0]["type"] == "text" and parts[1]["image_url"]["url"] == PNG
    assert c.seen[0]["model"] == agent.MODEL


def test_model_failure_on_card_is_friendly(monkeypatch):
    import agent
    from conftest import Scripted
    monkeypatch.delenv("MOCK_MODEL")
    monkeypatch.setattr(agent, "get_client", lambda: Scripted([RuntimeError("boom")]))
    r = extras.read_card(PNG)
    assert r["plan"] is None and "type your plan" in r["message"]


def test_voice_handshake_matches_the_api_format():
    h = extras.handshake("KEY", "Spanish")
    assert h["authorization"] == {"accessToken": "Bearer KEY"}
    assert h["audioEncoding"] == "PCM_24KHZ" and h["model"] == "muse-voice-transcribe-1.0"
    assert h["languageBias"] == ["Spanish"] and h["mode"] == "ENDPOINTING"
    assert "languageBias" not in extras.handshake("KEY", "Klingon")
    assert extras.handshake("KEY", "English", ["A"])["keywords"] == ["A"] and "keywords" not in h


def test_voice_only_ready_with_a_real_key(monkeypatch):
    assert extras.voice_ready() is False                      # mock mode
    monkeypatch.delenv("MOCK_MODEL")
    monkeypatch.setenv("MODEL_API_KEY", "k")
    assert extras.voice_ready() is True
    monkeypatch.delenv("MODEL_API_KEY")
    assert extras.voice_ready() is False
