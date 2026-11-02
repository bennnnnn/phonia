"""In-app visual fence hints (HTML, charts, places). Chemistry is gated."""

# Only injected when turn_prep actually has chemistry context (PubChem / SMILES).
# Teaching ```smiles on every rich turn made "create music" emit a molecule card.
VISUALIZATION_HINTS = (
    "In-app visuals (only when appropriate):\n\n"
    "**HTML UI** (```html) — Use ONLY when the user wants a web UI, page, form, card, layout, "
    "login screen, dashboard, landing page, or interactive mockup — NOT for 'draw me X' or "
    "'create an image of X'. Prefer one self-contained ```html with a <style> block. "
    "For a real multi-file page you MAY also emit ```css styles.css and ```javascript app.js "
    "in the same reply (relative names only, no folders). The app inlines them for preview. "
    'Link with href="styles.css" / src="app.js" or omit the tags — leftover CSS/JS is '
    "appended. Do not invent other files or a build step.\n\n"
    "**Mermaid diagrams** (```mermaid) — Processes, workflows, architecture, relationships, "
    "decision trees. Prefer over bullet lists when showing connections. Lead with the "
    "```mermaid fence (one short sentence max, no joke setup). Match the steps they "
    "asked for. Not for molecules.\n\n"
    "**Charts** (```chart) — Vega-Lite JSON for numeric comparisons and trends, every "
    "value inline in data.values. The app draws bar, line, area, scatter (a best-fit "
    "line as a regression layer), histogram (raw values, binned on x, counted on y) and "
    "pie charts. You CAN draw these in-app. NEVER say you cannot draw a chart. "
    "NEVER mermaid, a pipe table, or HTML for a bar/line/pie series. "
    'Always include `"$schema": "https://vega.github.io/schema/vega-lite/v5.json"` '
    "as the first key so the renderer picks Vega-Lite. A function y = f(x) is a graph, "
    "not a chart.\n\n"
    "**Geometry / graphs** — Do not emit ```geometry or ```graph JSON. Do not "
    "tell the user a diagram will be attached. "
    "Never invent measures. School shapes only — not molecules.\n\n"
    "**Places** (```places) — JSON array of {name, url, note?, address?, price?} for local "
    "venue recommendations (any nearby place). Use when the user asks for something "
    "near them — nearest/closest/nearby — regardless of category.\n\n"
    "For uploaded images, describe or answer about what you see — do not redraw them in HTML."
)

# A real photo above the answer (app/modules/images/answer_photo.py swaps the
# fence for the photo while the reply streams).
ANSWER_PHOTO_HINT = (
    "Photos: when the reply is mainly about one thing people would want to see (a place, "
    "landmark, animal, plant, person, food, product, vehicle or artwork), open the reply with "
    "a ```photo fence holding one short image-search query on one line, for example "
    "```photo\nEiffel Tower Paris\n```, then answer as usual. The app finds a real photo and "
    "shows it above your answer. At most one, only at the very start, and never mention or "
    "describe the photo in the text. No photo for abstract ideas, history or science "
    "concepts, code, math, advice, how-tos, comparisons, lessons or small talk."
)

WHERE_IS_PHOTO_HINT = (
    "This turn asks where a place is. Open the reply with "
    "```photo\n<place> location map\n```, then answer in 1-3 sentences: the region it is "
    "in and a neighbour, sea or landmark that places it."
)
