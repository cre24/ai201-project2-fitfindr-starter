"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

from tools import search_listings, suggest_outfit, create_fit_card, compare_price, _get_groq_client

import json


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
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """

    # Step 1: Initialize the session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query using the LLM to extract description, size, max_price
    client = _get_groq_client()

    try:
        parse_response = client.chat.completions.create(
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
                {
                    "role": "user",
                    "content": query,
                },
            ],
        )
        raw = parse_response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
    except Exception:
        parsed = {"description": query, "size": None, "max_price": None}

    session["parsed"] = parsed

    description = parsed.get("description", query)
    size = parsed.get("size")
    max_price = parsed.get("max_price")

    # Step 3: Call search_listings and return early if no results
    search_results = search_listings(description, size=size, max_price=max_price)
    session["search_results"] = search_results

    if not search_results:
        session["error"] = (
            "No listings found matching your search. Try broadening your description, "
            "adjusting your size, or increasing your budget."
        )
        return session

    # Step 4: Select top result, pass to compare_price (non-blocking)
    new_item = search_results[0]
    session["selected_item"] = new_item

    session["price_comparison"] = compare_price(new_item)

    # Step 5: Call suggest_outfit and return early if it fails
    outfit_suggestion = suggest_outfit(new_item, wardrobe)

    if not outfit_suggestion or outfit_suggestion.strip() == "Unable to suggest outfits at this time.":
        session["error"] = (
            "Unable to suggest an outfit at this time. "
            "Try adding more items to your wardrobe or searching for a different item."
        )
        return session

    session["outfit_suggestion"] = outfit_suggestion

    # Step 6: Call create_fit_card
    session["fit_card"] = create_fit_card(outfit_suggestion, new_item)

    # Step 7: Return the session
    return session


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
