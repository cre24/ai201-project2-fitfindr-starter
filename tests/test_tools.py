"""
Tests for the FitFindr tools.

Run from the project root:
    pytest tests/test_tools.py -v

The LLM-backed tools (suggest_outfit, create_fit_card, compare_price) are tested
with a mocked Groq client, so the suite runs fully offline and never spends
tokens or depends on network availability. search_listings is exercised directly
against the bundled mock dataset.
"""

import pytest
from unittest.mock import MagicMock, patch

from tools import (
    search_listings,
    suggest_outfit,
    create_fit_card,
    compare_price,
)
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

EXPECTED_KEYS = {"title", "price", "brand", "condition"}

GRAPHIC_TEE = {
    "title": "Graphic Tee — 2003 Tour Bootleg Style",
    "price": 24.0,
    "brand": None,
    "condition": "good",
}


def _fake_groq_client(content: str = "mocked styling response"):
    """Build a Groq-client stand-in whose chat completion returns `content`."""
    client = MagicMock()
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client.chat.completions.create.return_value = response
    return client


# ── Tool 1: search_listings ────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0
    # The most relevant hit should clearly be a graphic tee/top, and every
    # result must respect the price ceiling.
    assert "graphic" in results[0]["title"].lower()
    assert all(item["price"] <= 50 for item in results)


def test_search_results_have_only_the_contract_keys():
    results = search_listings("denim jeans")
    assert results
    for item in results:
        assert set(item.keys()) == EXPECTED_KEYS


def test_search_returns_at_most_three():
    assert len(search_listings("vintage")) <= 3


def test_search_ranks_best_match_first():
    results = search_listings("vintage denim jeans")
    assert results
    assert "jeans" in results[0]["title"].lower()


def test_search_size_filter_is_case_insensitive_substring():
    # 'm' should match sizes like 'S/M' without raising on a lowercase string.
    results = search_listings("top shirt", size="m")
    assert isinstance(results, list)


def test_search_no_match_returns_empty_list():
    assert search_listings("zzzqqq nonexistent garment") == []


def test_search_blank_description_returns_empty_list():
    assert search_listings("") == []
    assert search_listings("   ") == []


def test_search_impossible_price_returns_empty_list():
    assert search_listings("denim jeans", max_price=0.01) == []


def test_search_respects_max_price():
    cap = 30.0
    results = search_listings("denim", max_price=cap)
    assert all(item["price"] <= cap for item in results)


def test_search_unmatched_size_returns_empty_list():
    assert search_listings("jeans", size="XXXS-not-real") == []


def test_search_always_returns_a_list():
    assert isinstance(search_listings("anything"), list)


# ── Tool 2: suggest_outfit ─────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe_returns_text():
    with patch("tools._get_groq_client", return_value=_fake_groq_client("Pair it with jeans.")):
        result = suggest_outfit(GRAPHIC_TEE, get_example_wardrobe())
    assert isinstance(result, str) and result.strip()


def test_suggest_outfit_empty_wardrobe_returns_text():
    with patch("tools._get_groq_client", return_value=_fake_groq_client("Style it with sneakers.")):
        result = suggest_outfit(GRAPHIC_TEE, get_empty_wardrobe())
    assert isinstance(result, str) and result.strip()


def test_suggest_outfit_empty_new_item_returns_text():
    with patch("tools._get_groq_client", return_value=_fake_groq_client("General styling advice.")):
        result = suggest_outfit({}, get_example_wardrobe())
    assert isinstance(result, str) and result.strip()


# ── Tool 3: create_fit_card ────────────────────────────────────────────────────

def test_create_fit_card_returns_caption():
    outfit_suggestion = (
        "Pair the Graphic Tee with baggy straight-leg jeans and chunky white "
        "sneakers for a relaxed, retro-inspired look."
    )
    with patch("tools._get_groq_client", return_value=_fake_groq_client("Found this tee for $24 — wore it with my favorite jeans.")):
        result = create_fit_card(outfit_suggestion, GRAPHIC_TEE)
    assert isinstance(result, str) and result.strip()


def test_create_fit_card_empty_outfit_returns_error_string():
    # No LLM call should happen on the empty-outfit guard path.
    result = create_fit_card("", GRAPHIC_TEE)
    assert result == "Unable to create a caption — no outfit suggestion was provided. Please try again."


def test_create_fit_card_empty_new_item_returns_text():
    outfit_suggestion = "Pair with baggy jeans and chunky sneakers for a 90s look."
    with patch("tools._get_groq_client", return_value=_fake_groq_client("Throwback fit, all thrifted.")):
        result = create_fit_card(outfit_suggestion, {})
    assert isinstance(result, str) and result.strip()


# ── Tool 4: compare_price ──────────────────────────────────────────────────────

def test_compare_price_with_dataset_returns_text():
    with patch("tools._get_groq_client", return_value=_fake_groq_client("Fair price — similar tees average $22.")):
        result = compare_price(GRAPHIC_TEE)
    assert isinstance(result, str) and result.strip()


def test_compare_price_empty_dataset_returns_text():
    # Empty dataset short-circuits before any LLM call — no client needed.
    with patch("tools.load_listings", return_value=[]):
        result = compare_price(GRAPHIC_TEE)
    assert isinstance(result, str) and result.strip()


def test_compare_price_empty_new_item_returns_text():
    with patch("tools._get_groq_client", return_value=_fake_groq_client("Hard to compare without details.")):
        result = compare_price({})
    assert isinstance(result, str) and result.strip()
