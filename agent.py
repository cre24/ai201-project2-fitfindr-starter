"""
agent.py

The FitFindr planning loop. Orchestrates the tools in response to a natural
language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json

from tools import search_listings, suggest_outfit, create_fit_card, compare_price, _get_groq_client


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "price_comparison": None,    # string returned by price_comparison
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
        "search_note": None,         # sets context for the user if no direct matches
    }


# ── LLM helpers ───────────────────────────────────────────────────────────────

_OUTFIT_FAILURE = "Unable to suggest outfits at this time."

_OUTFIT_ERROR_MSG = (
    "Unable to suggest an outfit at this time. "
    "Try adding more items to your wardrobe or searching for a different item."
)


def _classify_intent(query: str) -> str:
    """Classify which tool a query wants. Defaults to 'search_listings' on error.

    Only consulted when the session already carries a selected item, since that
    is the only case where a non-search intent (e.g. price-only) changes routing.
    """
    if not query or not query.strip():
        return "search_listings"
    try:
        response = _get_groq_client().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an intent classifier for a thrift shopping assistant. "
                        "Given a user query, return ONLY one of these four tool names with no explanation:\n"
                        "- search_listings: user wants to find a clothing item\n"
                        "- suggest_outfit: user already has an item and wants outfit ideas\n"
                        "- compare_price: user wants to know if a price is fair\n"
                        "- create_fit_card: user wants a caption for an outfit they already have\n"
                        "Return only the tool name, nothing else."
                    ),
                },
                {"role": "user", "content": query},
            ],
        )
        return (response.choices[0].message.content or "search_listings").strip()
    except Exception:
        return "search_listings"


def _parse_query(query: str) -> dict:
    """Extract description / size / max_price from a query. Falls back to the
    raw query as the description if the LLM call or JSON parse fails."""
    try:
        response = _get_groq_client().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a query parser for a thrift shopping assistant. "
                        "Extract the item description, size, and max price from the user's query. "
                        "Respond ONLY with a JSON object with exactly these keys: "
                        "description (str), size (str or null), max_price (float or null). "
                        "No preamble, no markdown, no explanation — just the JSON object."
                    ),
                },
                {"role": "user", "content": query},
            ],
        )
        return json.loads(response.choices[0].message.content or "{}")
    except Exception:
        return {"description": query, "size": None, "max_price": None}


def _run_outfit_pipeline(session: dict) -> dict:
    """Run compare_price → suggest_outfit → create_fit_card for the selected item.

    Sets session['error'] and returns early (without a fit card) if the outfit
    suggestion fails. compare_price is non-blocking — its result is kept even if
    later steps fail.
    """
    item = session["selected_item"]
    session["price_comparison"] = compare_price(item)

    outfit_suggestion = suggest_outfit(item, session["wardrobe"])
    if not outfit_suggestion or outfit_suggestion.strip() == _OUTFIT_FAILURE:
        session["error"] = _OUTFIT_ERROR_MSG
        return session

    session["outfit_suggestion"] = outfit_suggestion
    session["fit_card"] = create_fit_card(outfit_suggestion, item)
    return session


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict, session_state: dict | None = None) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:         Natural language user request
        wardrobe:      User's wardrobe dict
        session_state: Optional pre-populated session state. If provided,
                       the planning loop will skip tools whose inputs are
                       already satisfied and dispatch to the appropriate
                       tool directly.

    Returns:
        The session dict after the interaction completes.
    """

    # Step 1: Initialize the session
    session = _new_session(query, wardrobe)

    # Merge any pre-populated state
    if session_state:
        session.update(session_state)

    # Step 2: Dispatch from pre-populated state. This only applies to the
    # programmatic API — the Gradio UI always starts from a fresh search, so
    # the common path skips the intent-classification LLM call entirely.
    if session.get("outfit_suggestion") and session.get("selected_item"):
        # Outfit already chosen — just generate the shareable caption.
        session["fit_card"] = create_fit_card(session["outfit_suggestion"], session["selected_item"])
        return session

    if session.get("selected_item"):
        # An item is in hand. Use intent to tell "is this a fair price?" apart
        # from the full styling pipeline.
        if _classify_intent(query) == "compare_price":
            session["price_comparison"] = compare_price(session["selected_item"])
            return session
        return _run_outfit_pipeline(session)

    # Default: start at search_listings.
    # Step 3: Parse the query to extract description, size, max_price.
    parsed = _parse_query(query)
    session["parsed"] = parsed

    description = parsed.get("description", query)
    size = parsed.get("size")
    max_price = parsed.get("max_price")

    # Step 4: Call search_listings with retry logic
    search_results = search_listings(description, size=size, max_price=max_price)

    # Attempt 2: drop size
    if not search_results and size is not None:
        search_results = search_listings(description, size=None, max_price=max_price)
        if search_results:
            session["search_note"] = f"No results found for size {size} — showing results for all sizes instead."

    # Attempt 3: drop max_price
    if not search_results and max_price is not None:
        search_results = search_listings(description, size=size, max_price=None)
        if search_results:
            session["search_note"] = f"No results found under ${max_price} — showing results at any price instead."

    # Attempt 4: description only
    if not search_results:
        search_results = search_listings(description, size=None, max_price=None)
        if search_results:
            session["search_note"] = "No results matched your size and price filters — showing the closest matches instead."

    # All attempts exhausted
    if not search_results:
        session["error"] = "No listings found even after loosening size and price filters. Try a broader description."
        return session

    session["search_results"] = search_results

    # Step 5: Select the top result, then run compare_price → suggest_outfit →
    # create_fit_card. Returns early with an error if no outfit can be suggested.
    session["selected_item"] = search_results[0]
    return _run_outfit_pipeline(session)


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\n--- session['selected_item'] ---")
        print(session["selected_item"])
        print(f"\n--- session['price_comparison'] ---")
        print(session["price_comparison"])
        print(f"\n--- session['outfit_suggestion'] ---")
        print(session["outfit_suggestion"])
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
    print(f"fit_card is None: {session2['fit_card'] is None}")
    print(f"outfit_suggestion is None: {session2['outfit_suggestion'] is None}")
    print(f"price_comparison is None: {session2.get('price_comparison') is None}")

    print("\n\n=== Retry logic path ===\n")
    session3 = run_agent(
        query="vintage graphic tee size XXXS under $1",
        wardrobe=get_example_wardrobe(),
    )
    if session3["error"]:
        print(f"Error message: {session3['error']}")
    else:
        print(f"Found: {session3['selected_item']['title']}")
        print(f"Search note: {session3['search_note']}")

    print("\n\n=== Direct suggest_outfit path ===\n")
    session4 = run_agent(
        query="",
        wardrobe=get_example_wardrobe(),
        session_state={
            "selected_item": {"title": "Graphic Tee — 2003 Tour Bootleg Style", "price": 24.0, "brand": None, "condition": "good"}
        }
    )
    if session4["error"]:
        print(f"Error: {session4['error']}")
    else:
        print(f"Outfit: {session4['outfit_suggestion']}")
        print(f"Fit card: {session4['fit_card']}")

    print("\n\n=== Direct create_fit_card path ===\n")
    session5 = run_agent(
        query="",
        wardrobe=get_example_wardrobe(),
        session_state={
            "selected_item": {"title": "Graphic Tee — 2003 Tour Bootleg Style", "price": 24.0, "brand": None, "condition": "good"},
            "outfit_suggestion": "Pair with baggy straight-leg jeans and chunky white sneakers for a 90s look."
        }
    )
    if session5["error"]:
        print(f"Error: {session5['error']}")
    else:
        print(f"Fit card: {session5['fit_card']}")