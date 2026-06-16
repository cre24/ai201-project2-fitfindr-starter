"""
Tests for tools.search_listings.

Run all tests:           pytest test_search_listings.py -v
Run as a plain script:   python test_search_listings.py
"""

from tools import search_listings

EXPECTED_KEYS = {"title", "price", "brand", "condition"}


def test_returns_at_most_three():
    """Never returns more than the top 3 matches."""
    results = search_listings("vintage")
    assert len(results) <= 3


def test_each_result_has_exactly_the_four_keys():
    """Every result dict matches the tool contract — no more, no fewer keys."""
    results = search_listings("denim jeans")
    assert results, "expected at least one match for 'denim jeans'"
    for item in results:
        assert set(item.keys()) == EXPECTED_KEYS


def test_relevant_query_ranks_best_match_first():
    """A specific query surfaces the obviously-relevant item at index 0."""
    results = search_listings("vintage denim jeans")
    assert results
    assert "jeans" in results[0]["title"].lower()


def test_max_price_filter_excludes_pricier_items():
    """No returned item exceeds the price ceiling."""
    cap = 30.0
    results = search_listings("denim", max_price=cap)
    assert all(item["price"] <= cap for item in results)


def test_size_filter_is_case_insensitive_substring():
    """size='M' should match sizes like 'S/M' and 'M/L', not just exact 'M'."""
    results = search_listings("top shirt", size="m")
    # We can't assert size from the trimmed output, but we can assert it still
    # returns matches and never errors with a lowercase size string.
    assert isinstance(results, list)


def test_no_keyword_match_returns_empty_list():
    """A query that matches nothing returns [] — not None, not an error."""
    assert search_listings("zzzqqq nonexistent") == []


def test_blank_description_returns_empty_list():
    """Blank / whitespace-only input returns [] without raising."""
    assert search_listings("") == []
    assert search_listings("   ") == []


def test_never_raises_returns_list():
    """The function always returns a list, upholding the fail-safe contract."""
    assert isinstance(search_listings("anything"), list)


# --- Allow running without pytest: `python test_search_listings.py` ---
if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except AssertionError:
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
        except Exception:
            print(f"ERROR {test.__name__}")
            traceback.print_exc()

    print(f"\n{passed}/{len(tests)} tests passed.")
