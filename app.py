"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up —
your job is to fill in handle_query() so it calls run_agent() and maps
the session results to the three output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:      The text the user typed into the search box.
        wardrobe_choice: Either "Example wardrobe" or "Empty wardrobe (new user)".

    Returns:
        A tuple of four strings:
            (listing_text, price_check, outfit_suggestion, fit_card)
        Each string maps to one of the four output panels in the UI.
    """
    # Step 1: Guard against empty query
    if not user_query or not user_query.strip():
        return "Please enter a search query to get started.", "", "", ""

    # Step 2: Select wardrobe based on choice
    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    # Step 3: Call run_agent
    session = run_agent(user_query, wardrobe)

    # Step 4: Return error in first panel if something went wrong
    if session["error"]:
        return session["error"], "", "", ""

    # Step 5: Format selected_item into a readable listing string
    item = session["selected_item"]
    price = item.get("price")
    price_str = f"${price}" if isinstance(price, (int, float)) else "N/A"

    listing_text = (
        f"Title:      {item.get('title', 'N/A')}\n"
        f"Price:      {price_str}\n"
        f"Brand:      {item.get('brand') or 'Unbranded'}\n"
        f"Condition:  {item.get('condition', 'N/A')}\n"
    )

    if session.get("search_note"):
        listing_text += f"\nNote: {session['search_note']}"

    price_check = session.get("price_comparison") or ""

    return listing_text, price_check, session["outfit_suggestion"], session["fit_card"]


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        # Row 1 — the find and whether it's worth it.
        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            price_output = gr.Textbox(
                label="💰 Price check",
                lines=8,
                interactive=False,
            )

        # Row 2 — how to wear it.
        with gr.Row():
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, price_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, price_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
