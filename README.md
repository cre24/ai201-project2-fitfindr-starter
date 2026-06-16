# FitFindr

FitFindr is a thrift shopping assistant that takes a natural language query, searches a dataset of secondhand listings, suggests outfit combinations based on the user's wardrobe, and generates a shareable social media caption.

---

## Tool Inventory

### Tool 1: `search_listings`
- **Inputs:** `description` (str), `size` (str | None), `max_price` (float | None)
- **Output:** `list[dict]` — up to 3 listing dicts, each with `title` (str), `price` (float), `brand` (str | None), `condition` (str), sorted by relevance
- **Purpose:** Queries the listings dataset and returns the top matching items based on keyword overlap with the description, filtered by size and price ceiling. This is the entry point of the planning loop — if it returns empty, the flow stops.

---

### Tool 2: `suggest_outfit`
- **Inputs:** `new_item` (dict), `wardrobe` (dict)
- **Output:** `str` — 1-2 outfit combinations pairing the new item with wardrobe pieces, with a concrete styling tip
- **Purpose:** Takes the top listing and the user's wardrobe and asks the LLM to suggest specific outfit combinations. If the wardrobe is empty, it falls back to general styling advice for the item rather than failing.

---

### Tool 3: `create_fit_card`
- **Inputs:** `outfit` (str), `new_item` (dict)
- **Output:** `str` — a 2-4 sentence Instagram/TikTok-style caption
- **Purpose:** Converts the outfit suggestion into a casual, first-person social media caption that mentions the item name, price, and source naturally. Uses a higher LLM temperature (0.9) so captions feel distinct across different inputs.

---

### Tool 4: `compare_price`
- **Inputs:** `new_item` (dict)
- **Output:** `str` — a 2-3 sentence price verdict referencing comparable items from the dataset
- **Purpose:** Loads the listings dataset internally and benchmarks the selected item's price against similar items by category, condition, and style. Returns a verdict (good deal, fair price, or overpriced) with supporting evidence. Non-blocking — a failure here does not stop the flow.

---

## Planning Loop

When a user submits a query, the agent does not always start at the same tool. Instead, a planning loop evaluates what inputs are available and dispatches to the appropriate tool:

1. The user query is parsed by the LLM to extract `description`, `size`, and `max_price`
2. `search_listings` is called first — it is the only required entry point since all downstream tools depend on its output
3. If `search_listings` returns results, `new_item = results[0]` is stored and passed to both `compare_price` and `suggest_outfit`
4. `compare_price` runs as a non-blocking annotation — its result is stored but a failure does not stop the flow
5. If `suggest_outfit` succeeds, its output is passed to `create_fit_card`
6. The completed session is returned

The flow only travels downward. No tool re-prompts the user or re-fetches data from a previous step.

---

## State Management

After each tool call, the output is stored in the session dict and passed explicitly to the next tool as a named variable. Nothing is re-fetched or re-computed between steps.

| Session key | Set by | Passed to |
|---|---|---|
| `session["parsed"]` | LLM query parser | `search_listings` |
| `session["search_results"]` | `search_listings` | used to set `selected_item` |
| `session["selected_item"]` | planning loop (`results[0]`) | `suggest_outfit`, `compare_price` |
| `session["price_comparison"]` | `compare_price` | displayed in listing panel |
| `session["outfit_suggestion"]` | `suggest_outfit` | `create_fit_card` |
| `session["fit_card"]` | `create_fit_card` | returned in session |
| `session["error"]` | any failed step | triggers early return |

The user's wardrobe is captured at the start of the session and held in memory for the duration of the interaction — it is never re-loaded between steps.

---

## Error Handling

Each tool handles failures independently and returns a descriptive string rather than raising an exception, so the agent always has one consistent path for handling "no results."

**`search_listings`** — if no listings match, returns an empty list. The planning loop catches this and sets `session["error"]` with a message telling the user what to try differently. No further tools are called.

> Concrete example: querying `"designer ballgown size XXS under $5"` returned `[]`. The agent set `session["error"]` to `"No listings found matching your search. Try broadening your description, adjusting your size, or increasing your budget."` and `session["fit_card"]` remained `None`, confirming `suggest_outfit` and `create_fit_card` were never called.

**`suggest_outfit`** — if the wardrobe is empty, the LLM is prompted for general styling advice instead of specific pairings, so the function always returns a non-empty string. If the LLM call itself fails, it returns `"Unable to suggest outfits at this time."` and the planning loop sets `session["error"]` and returns early.

> Concrete example: passing `get_empty_wardrobe()` returned general styling advice ("Pair with high-waisted jeans or black joggers for a laid-back look") rather than crashing or returning an empty string.

**`create_fit_card`** — guards against an empty `outfit` string before calling the LLM. If `outfit` is empty or whitespace-only, it returns `"Unable to create a caption — no outfit suggestion was provided. Please try again."` without making an API call.

> Concrete example: calling `create_fit_card("", new_item)` returned the error string immediately, confirmed by `test_create_fit_card_empty_outfit_returns_error_string`.

**`compare_price`** — if the dataset is empty or the LLM call fails, it returns a descriptive string and the flow continues. It never blocks `suggest_outfit` or `create_fit_card`.

> Concrete example: patching `load_listings` to return `[]` via `unittest.mock.patch("tools.load_listings", return_value=[])` returned `"No dataset available to compare against. Try checking platforms like Depop, Poshmark, or eBay for similar listings."` and the rest of the session completed normally.

---

## Spec Reflection

**What matched the spec:** The core flow matched closely — `search_listings` as the gatekeeper, `new_item = results[0]` set at the planning level, and `compare_price` as a non-blocking annotation that never gates downstream tools. The state management approach of storing each output in a named session key before passing it forward kept the tools fully decoupled.

**What required adjustment:** The original spec described `compare_price` as taking both `new_item` and `dataset` as inputs. During implementation, the dataset input was removed and replaced with an internal `load_listings()` call, consistent with how `search_listings` handles data loading. This simplified the planning loop since the dataset did not need to be loaded and passed at the agent level.

**What was harder than expected:** The empty wardrobe edge case for `suggest_outfit` required two distinct LLM prompts — one for a populated wardrobe referencing specific pieces by name, and one for an empty wardrobe giving general styling advice. A single prompt could not handle both cases well because the LLM would either hallucinate wardrobe pieces or give overly generic advice when pieces were available.

---

## AI Usage

**Instance 1 — `compare_price` input parameter design**

I provided the tool spec for `compare_price` describing it as taking both `new_item` and `dataset` as inputs, and asked Claude to implement the function. It produced a working implementation that accepted `dataset` as a parameter and expected it to be passed in from the planning loop. I overrode this design before using it — I removed the `dataset` parameter entirely and replaced it with an internal `load_listings()` call inside the function, consistent with how `search_listings` already handled data loading. This change simplified the planning loop since the dataset no longer needed to be loaded and passed at the agent level, and it kept each tool self-contained. The updated function signature went from `compare_price(new_item: dict, dataset: dict)` to `compare_price(new_item: dict)`.

**Instance 2 — `suggest_outfit` implementation**

I provided the tool spec (inputs, outputs, error handling behavior, the Groq model to use) and the wardrobe schema from `data/wardrobe_schema.json` and asked Claude to implement the function. It produced a working implementation but used `item.get("title")` and `item.get("type")` to format wardrobe items — neither of which matched the actual schema keys (`name` and `category`). I identified this by printing `get_example_wardrobe()` to inspect the real structure, then corrected the field names to `item.get("name")` and `item.get("category")`. The fix caused the LLM to reference specific wardrobe pieces by name in its suggestions rather than falling back to the empty wardrobe path.