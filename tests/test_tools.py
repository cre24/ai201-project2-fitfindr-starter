"""
Tests for the FitFindr tools.

Run from the project root:
    pytest tests/test_tools.py -v

NOTE: Only search_listings is implemented so far. The tests for
suggest_outfit, create_fit_card, and compare_price are marked xfail
("expected to fail until implemented") — they document the intended
behaviour now and will start passing once those tools are built out.
"""

import pytest
from unittest.mock import patch

from tools import (
    search_listings,
    suggest_outfit,
    create_fit_card,
    compare_price,
)
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

EXPECTED_KEYS = {"title", "price", "brand", "condition"}


# ── Tool 1: search_listings ────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    expected_result = [{'title': 'Graphic Tee — 2003 Tour Bootleg Style', 'price': 24.0, 'brand': None, 'condition': 'good'}, {'title': 'Vintage Graphic Hoodie — Faded Black', 'price': 26.0, 'brand': None, 'condition': 'fair'}, {'title': 'Vintage Band Tee — Faded Grey', 'price': 19.0, 'brand': None, 'condition': 'fair'}]
    assert isinstance(results, list)
    assert len(results) > 0
    assert results == expected_result


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


# ── Tool 2: suggest_outfit ─────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe_returns_text():
    new_item = {'title': 'Graphic Tee — 2003 Tour Bootleg Style', 'price': 24.0, 'brand': None, 'condition': 'good'}
    result = suggest_outfit(new_item, get_example_wardrobe())
    assert isinstance(result, str) and result.strip()


def test_suggest_outfit_empty_wardrobe_returns_text():
    new_item = {'title': 'Graphic Tee — 2003 Tour Bootleg Style', 'price': 24.0, 'brand': None, 'condition': 'good'}
    result = suggest_outfit(new_item, get_empty_wardrobe())
    assert isinstance(result, str) and result.strip()


def test_suggest_outfit_empty_new_item_returns_text():
    result = suggest_outfit({}, get_example_wardrobe())
    assert isinstance(result, str) and result.strip()


# ── Tool 3: create_fit_card ────────────────────────────────────────────────────

def test_create_fit_card_returns_caption():
    new_item = {'title': 'Graphic Tee — 2003 Tour Bootleg Style', 'price': 24.0, 'brand': None, 'condition': 'good'}
    outfit_suggestion = "Here are two outfit combinations using the Graphic Tee: 1. **Casual Weekend Look**: Pair the Graphic Tee with the **Baggy straight-leg jeans** and **Chunky white sneakers**. This outfit creates a relaxed, retro-inspired look. Styling tip: Tuck the front of the Graphic Tee into the jeans to add a touch of nostalgia and emphasize the bootleg tour design. 2. **Edgy Evening Look**: Combine the Graphic Tee with the **Vintage black denim jacket** and **Black combat boots**. This outfit gives off a cool, grungy vibe. Styling tip: Layer the Graphic Tee under the denim jacket and leave it slightly unzipped to showcase the tour design and add a laid-back touch to the overall look."
    result = create_fit_card(outfit_suggestion, new_item)
    assert isinstance(result, str) and result.strip()


def test_create_fit_card_empty_outfit_returns_error_string():
    new_item = {'title': 'Graphic Tee — 2003 Tour Bootleg Style', 'price': 24.0, 'brand': None, 'condition': 'good'}
    result = create_fit_card("", new_item)
    assert isinstance(result, str) and result.strip()
    assert result == "Unable to create a caption — no outfit suggestion was provided. Please try again."


def test_create_fit_card_empty_new_item_returns_text():
    outfit_suggestion = "Pair with baggy jeans and chunky sneakers for a 90s look."
    result = create_fit_card(outfit_suggestion, {})
    assert isinstance(result, str) and result.strip()


# ── Tool 4: compare_price ──────────────────────────────────────────────────────

def test_compare_price_with_dataset_returns_text():
    new_item = {'title': 'Graphic Tee — 2003 Tour Bootleg Style', 'price': 24.0, 'brand': None, 'condition': 'good'}
    result = compare_price(new_item)
    assert isinstance(result, str) and result.strip()


def test_compare_price_empty_dataset_returns_text():
    new_item = {'title': 'Graphic Tee — 2003 Tour Bootleg Style', 'price': 24.0, 'brand': None, 'condition': 'good'}
    with patch("tools.load_listings", return_value=[]):
        result = compare_price(new_item)
    assert isinstance(result, str) and result.strip()


def test_compare_price_empty_new_item_returns_text():
    result = compare_price({})
    assert isinstance(result, str) and result.strip()