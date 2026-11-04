"""Tests for checks.py, the code that catches made-up doctors and made-up quotes.
Think of these as attacks: if one gets through, the check is broken."""
import checks as C

REVIEWS = ["She listens carefully and never rushes us.", "Hard to reach by phone, but the visit was great!"]


def test_exact_quote_passes_even_with_different_case_and_punctuation():
    assert C.quote_in_sources("she LISTENS carefully, and never rushes us", REVIEWS)
    assert C.quote_in_sources("Hard to reach by phone but the visit was great", REVIEWS)


def test_curly_quotes_and_dashes_are_treated_the_same():
    assert C.quote_in_sources("Doctor’s “kind” — really", ["Doctor's \"kind\" - really"])


def test_made_up_quote_fails():
    assert not C.quote_in_sources("the best doctor in the whole world", REVIEWS)


def test_changed_word_fails():
    assert not C.quote_in_sources("She listens carefully and always rushes us", REVIEWS)


def test_quote_must_be_inside_one_review_not_stitched_across_two():
    assert not C.quote_in_sources("never rushes us Hard to reach by phone", REVIEWS)


def test_ellipsis_allows_skipping_words_but_each_piece_must_be_real():
    assert C.quote_in_sources("She listens carefully ... never rushes us", REVIEWS)
    assert not C.quote_in_sources("She listens carefully ... and cures everything", REVIEWS)


def test_empty_sources_means_nothing_can_be_verified():
    assert not C.quote_in_sources("she listens carefully and never rushes", [])


def test_extract_quotes_ignores_short_phrases_like_plan_names():
    ans = 'Takes "Aetna PPO". Patients say "She listens carefully and never rushes us".'
    assert C.extract_quotes(ans) == ["She listens carefully and never rushes us"]


def test_extract_quotes_handles_curly_quotes():
    assert C.extract_quotes("They said “very kind and always on time”.") == ["very kind and always on time"]


def test_unknown_names_flags_only_unseen_doctors():
    seen = {"Dr. Sofia Marino", "Dr. Maya Lee"}
    assert C.unknown_names("Dr. Sofia Marino is near. Dr. Zed Madeup is great.", seen) == ["Dr. Zed Madeup"]
    assert C.unknown_names("Dr. Maya Lee and Dr. Sofia Marino.", seen) == []
    assert C.unknown_names("No names here.", seen) == []
