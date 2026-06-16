"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
    compare_price(new_item, dataset)               -> str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

from utils.data_loader import load_listings

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        The top 3 matching listings, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each returned dict has exactly these fields:
        title (str), price (float), brand (str or None), condition (str)
    """
    try:
        listings = load_listings()

        # Filter by max_price if provided
        if max_price is not None:
            listings = [
                item for item in listings
                if isinstance(item.get("price"), (int, float))
                and item["price"] <= max_price
            ]

        # Filter by size if provided (case-insensitive substring match)
        if size is not None:
            size_lower = size.lower()
            listings = [
                item for item in listings
                if isinstance(item.get("size"), str)
                and size_lower in item["size"].lower()
            ]

        # Score each listing by keyword overlap with description
        keywords = set(description.lower().split())

        def score(item: dict) -> int:
            searchable = " ".join([
                item.get("title") or "",
                item.get("brand") or "",
                item.get("condition") or "",
            ]).lower()
            return sum(1 for keyword in keywords if keyword in searchable)

        scored = [
            (item, score(item)) for item in listings
        ]

        # Drop listings with no keyword matches
        scored = [(item, s) for item, s in scored if s > 0]

        # Sort by score descending and return top 3
        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            {
                "title":     item["title"],
                "price":     item["price"],
                "brand":     item.get("brand"),
                "condition": item["condition"],
            }
            for item, _ in scored[:3]
        ]

    except Exception:
        return []


def _score_listing(listing: dict, keywords: set[str]) -> int:
    """Score a listing by how many description keywords it matches.

    Title and style_tags are weighted more heavily than the free-text
    description, since they're the most reliable signal of relevance.
    """
    if not keywords:
        return 0

    # Weighted fields: (searchable text, points per matched keyword).
    fields = [
        (listing["title"], 3),
        (" ".join(listing["style_tags"]), 3),
        (listing["category"], 2),
        (" ".join(listing["colors"]), 2),
        (listing["brand"] or "", 2),
        (listing["description"], 1),
    ]

    score = 0
    for text, weight in fields:
        text_tokens = set(re.findall(r"[a-z0-9']+", text.lower()))
        score += weight * len(keywords & text_tokens)

    return score


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1-2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    item_description = (
        f"{new_item.get('title', 'clothing item')} "
        f"by {new_item.get('brand') or 'an unknown brand'}, "
        f"priced at ${new_item.get('price', 'unknown')}, "
        f"condition: {new_item.get('condition', 'unknown')}."
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        prompt = (
            f"A user just thrifted the following item: {item_description}\n\n"
            "They haven't added any wardrobe items yet. Give them 1-2 general "
            "styling ideas for this piece — what kinds of bottoms, shoes, or "
            "layers pair well with it, and what overall vibe or aesthetic it suits."
        )
    else:
        formatted_wardrobe = "\n".join(
            f"- {item.get('name', 'unknown item')} "
            f"({item.get('category', 'unknown type')}, {item.get('color', 'unknown color')})"
            for item in wardrobe_items
        )
        prompt = (
            f"A user just thrifted the following item: {item_description}\n\n"
            f"Here is their current wardrobe:\n{formatted_wardrobe}\n\n"
            "Suggest 1-2 specific outfit combinations using the new item paired "
            "with pieces from their wardrobe. Name the exact wardrobe pieces, "
            "describe the overall look, and give one concrete styling tip."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are FitFindr, a personal styling assistant that "
                        "specializes in thrifted and secondhand fashion. Keep "
                        "suggestions concise, specific, and practical."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )
        return response.choices[0].message.content or "Unable to suggest outfits at this time."

    except Exception as e:
        print(f"Groq error: {e}")
        return "Unable to suggest outfits at this time."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2-4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.
    """
    if not outfit or not outfit.strip():
        return "Unable to create a caption — no outfit suggestion was provided. Please try again."

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    item_name = new_item.get("title", "a thrifted item")
    item_price = new_item.get("price", "unknown")
    item_brand = new_item.get("brand") or "a thrift find"
    item_condition = new_item.get("condition", "")

    prompt = (
        f"A user thrifted the following item: '{item_name}' for ${item_price} "
        f"from {item_brand}, condition: {item_condition}.\n\n"
        f"They are wearing it like this: {outfit}\n\n"
        "Write a 2-4 sentence Instagram or TikTok caption for this outfit. "
        "Rules:\n"
        "- Sound like a real person posting their OOTD, not a product description\n"
        "- Mention the item name, price, and where it was thrifted naturally, once each\n"
        "- Capture the specific vibe of the outfit in casual language\n"
        "- No hashtags, no emojis, no generic filler phrases like 'slaying' or 'obsessed'\n"
        "- Every caption should feel distinct and specific to this exact outfit"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are FitFindr, a personal styling assistant that specializes "
                        "in thrifted and secondhand fashion. You write captions that sound "
                        "authentic, specific, and conversational — like a real person who "
                        "loves fashion, not a brand account."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.9,
        )
        return response.choices[0].message.content or "Unable to create a caption from the input provided. Please try again."

    except Exception as e:
        return "Unable to create a caption from the input provided. Please try again."
    
# ── Tool 4: compare_price ───────────────────────────────────────────────────

def compare_price(new_item: dict) -> str:
    """
    Given a thrifted item and a dataset, output a string that tells the user
    if the thrifted item is a good price compared to similar items in the dataset.

    Args:
        new_item: A listing dict (the item the user is considering buying).

    Returns:
        A non-empty string comparing prices.
        If the dataset is empty, inform the user there is no data to compare
        the thrifted item to and suggest they check other sources.
    """
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    try:
        listings = load_listings()
    except Exception:
        return (
            "Unable to load the dataset for comparison. "
            "Try checking platforms like Depop, Poshmark, or eBay for similar listings."
        )

    if not listings:
        return (
            f"No dataset available to compare '{new_item.get('title', 'this item')}' against. "
            "Try checking platforms like Depop, Poshmark, or eBay for similar listings."
        )

    item_name = new_item.get("title", "a thrifted item")
    item_price = new_item.get("price", "unknown")
    item_condition = new_item.get("condition", "unknown")
    item_brand = new_item.get("brand") or "unbranded"

    formatted_dataset = "\n".join(
        f"- {item.get('title', 'unknown')} | "
        f"${item.get('price', 'unknown')} | "
        f"condition: {item.get('condition', 'unknown')} | "
        f"brand: {item.get('brand') or 'unbranded'} | "
        f"category: {item.get('category', 'unknown')}"
        for item in listings
    )

    prompt = (
        f"A user is considering buying the following thrifted item:\n"
        f"- Title: {item_name}\n"
        f"- Price: ${item_price}\n"
        f"- Condition: {item_condition}\n"
        f"- Brand: {item_brand}\n\n"
        f"Here are similar items from the dataset:\n{formatted_dataset}\n\n"
        "Compare the price of the user's item to similar items in the dataset. "
        "Rules:\n"
        "- Identify the most comparable items by category, condition, and style\n"
        "- Give a clear verdict: good deal, fair price, or overpriced\n"
        "- Reference specific items from the dataset to support your verdict\n"
        "- Keep it to 2-3 sentences, conversational but informative\n"
        "- Include the average price of comparable items if possible"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are FitFindr, a personal styling assistant that specializes "
                        "in thrifted and secondhand fashion. You give honest, specific "
                        "price comparisons to help users decide if a thrifted item is "
                        "worth buying."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )
        return response.choices[0].message.content or "Unable to make a comparison at this time. The flow will continue."

    except Exception:
        return "Unable to make a comparison at this time. The flow will continue."
