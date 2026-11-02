# Recall maths pipeline

Server-side SymPy verifies and samples; the mobile app only renders. Do not add on-device solving.

Latest review and plan (workout format, coverage, models, geometry, scanner): [MATH_REVIEW.md](./MATH_REVIEW.md).

## Architecture and ownership audit

The chat pipeline chooses a peer subject before it extracts an intent:

```text
user input
→ neutral subject detection (`services/subjects/dispatch.py`)
→ math extraction (`modules/math/tools/extract.py`)
→ request-consumption audit (`modules/math/request_consumption.py`)
→ math solver and typed trace (`modules/math/solve/`, `modules/math/school.py`)
→ math direct reply OR math-only prompt context
→ math fence/finalization (`modules/math/fence.py`)
→ neutral streaming and persistence
→ mobile parsing/rendering
→ reopened message
→ Copy/share/read-aloud from the same persisted source
```

Physics takes the parallel physics path after neutral detection; it does not enter the math
extractor, builder, prompt, direct-reply, or fence. See
[SUBJECT_SEPARATION_TICKETS.md](./SUBJECT_SEPARATION_TICKETS.md).

| Stage | Owner | What may change correctness |
|---|---|---|
| Subject detection | Neutral dispatcher; math and physics provide their own gates | Selecting the wrong subject changes the entire grammar, so dispatch is tested before extraction. |
| Intent extraction | Math | Dropped terms, numbers, clauses, domains, units, or requested quantities. |
| Consumption audit | Math | Meaningful unconsumed material makes the deterministic path decline; polite wrappers do not. |
| Solver | Math | Produces the canonical answer and typed procedure; it cannot guess omitted givens. |
| Direct/prompt choice | Subject-neutral dispatch, math presentation | Response depth may change, never the canonical mathematics. |
| Prompt/model | Math context plus neutral safety | The model may explain verified data but cannot replace it or invent a verified trace. |
| Fence finalization | Math | Canonical fences replace model-authored copies; unsupported/partial work remains unverified. |
| Stream/persistence | Neutral chat | Must retain signs, exponents, roots, fractions, branches, domains, and source fences byte-for-byte where required. |
| Mobile render | Mobile presentation | Parses typed fences and math source; it never solves or infers a different expression. |
| Reopen/Copy/read-aloud | Shared client message surfaces | Reuses persisted canonical source rather than reconstructing mathematics from pixels. |

The request-consumption audit is the atomicity boundary. A multipart request such as “mean and
standard deviation” or “area and perimeter” is either represented completely or deliberately
falls back without claiming that one partial result answers the whole prompt.

## Default product path (heuristic SymPy, always)

1. **Heuristic pre-stream** ([`math/tools/`](../apps/api/app/modules/math/tools/)) — the gate (`match/needs.py`) asks its lexical `NEED_SIGNALS` first and a chosen few extractors last (`tools/extractors/detection.py`); every extractor reads a line once (`tools/extractors/readings.py`), so extraction reuses what the gate read. If `needs_symbolic_math`, SymPy runs in isolated worker slots (default 3; interactive slot wait 2s, then the 5s solve timeout). A verified system block is injected (numbers + `canonical_fence` / `canonical_answer` for ` ```geometry` / ` ```graph` / ` ```answer `). The hint tells the model **not** to emit those fences. When the gate fires but no regex extractor matches, one bounded structured-extraction call on the fast `gpt-6-luna` route (`math/tools/llm_extract.py`, flag `math_llm_extract_enabled`, 2.5s timeout) proposes a candidate `MathIntent` — it still has to survive SymPy, and only that already-failing path pays for the call. It is certified only when its equation or expression is one the user wrote, compared with SymPy as the tool loop's calls are (`tool_check.intent_in_user_text`): "divided by x + 1 … the remainder is 3" read as 9B = 3 was a checked A = -61/3 for A = 1 (2026-11-01). Algebra **word problems** (no equation to extract; `math/tools/word_problem.py`, flag `math_word_problems_enabled`, 3s timeout, at least one number in digits) get their own structured call that translates the problem into unknowns, equations and what is asked (`WordProblemSetup`). A few textbook shapes (consecutive integers, two ages, tickets at two prices, mixing to a target strength) are read without that call by `math/tools/word_templates.py`, which writes the same setup for the same checks. A provider timeout or malformed structured response gets one bounded retry through the existing independent fallback provider; neither provider can certify an answer. Every number in the translation must be stated in the problem (digits or words such as "twice", "half", "15%"; a 1 only when stated or inside a stated fraction or rate, as in `1/2` or `(1 - 0.2)`), and SymPy must find exactly one solution that fits the stated domain (whole numbers for counts, positive for ages and prices); otherwise the turn keeps its normal path. SymPy checks the arithmetic of a translation, not that it says what the problem says, so a translation is never a verified card: its setup (each equation with the words it comes from) and SymPy's solution go to the model as an unchecked setup to check against the problem (`tools/block/word.unchecked_setup_note`). Only a setup the templates read is certified. A process that never ends ("continues without end", "forever") gets no setup at all: three rounds of a tax were summed to 3920 Birr for 5000. A message with the student's own worked lines ("check my work" plus the lines, or a bare column running from a problem to an answer) is read on the raw text, before `prepare()` joins the lines.
2. **Direct verified reply** — short closed answers and supported plain graph requests can **skip the LLM** through the instant-reply seam. Whole literal requests for supported 2D measurements return the requested answer plus the canonical diagram; closed cube, rectangular-prism, cylinder, cone, sphere, and square-pyramid volume/surface-area requests return one answer with units. The guards require the requested dimensions, units, and quantity to agree with the verified result. An exact AAA drawing returns relative lengths only; an area/perimeter request with angles alone asks for a side length instead of inventing a scale. **Written arithmetic** stays on `MathIntent(kind="arithmetic")`: multi-addend addition carries, subtraction regrouping (including across zero), multiplication carries/partial products, and long-division quotient/subtract/bring-down/remainder state are exact server-owned trace data. Answer representation is separate from presentation: ordinary division returns the numerical quotient, while remainder/fraction/round-up/discard modes require an explicit cue; the written long-division trace appears only for a steps/method request. Decimal operands remain exact and aligned; terminating decimal division adds the visible placeholder zeros. `FractionWorkSpec` similarly owns simplifying, equivalence/comparison, four operations, mixed/improper conversion, and fraction-of-a-quantity working. The mobile app only lays out these traces. “Show steps” and an adjacent “how?” return the same canonical working; “just the answer” suppresses it. **Lessons** are server-rendered from verified `key_steps` (Given + one transformation per line + the ```answer chip) for every supported equation trace, independent of the global prose-length style; only an explicit “just the answer” request hides the working. A terse adjacent “how?” / “why?” / “show the steps” re-solves the prior equation and replays these same verified steps instead of asking the LLM for a new method. Covered lessons include linear, pure-power, and quadratic equations; linear and compound inequalities (with the flip when dividing by a negative, and the number line kept under the chip); 2×2 linear systems by substitution or elimination; derivatives rule by rule; indefinite integrals by method (power rule, standard forms, u-substitution, integration by parts). Every line of a trace is checked with SymPy before it is shown (same solution set, satisfied by the solution, or differentiated back); a trace with a line that fails is dropped whole. **Check my work** replies mark each of the student's lines, name the first slip, and continue from the corrected line with a verified trace; hint mode (“don't finish it for me”) names the slip as a question and never shows the fix or the answer. **Word problems** a template read reply with the setup (what each letter stands for, and the words each equation comes from), the verified steps, and the answer. Explanations that have no trace, hints, mixed/qualified requests, camera homework, and requests outside these complete grammars retain the model response path.
3. **LLM stream** (when language adds value) — model answers briefly in Markdown + `$...$`. A reply instruction immediately after the verified working distinguishes supporting solver data from a user request for teaching.
4. **Post-stream** ([`math/fence.py`](../apps/api/app/modules/math/fence.py)) — rewrite any leftover arithmetic/geometry/graph/`answer` fences from the model with the canonical body; append missing solver-owned results. The verified answer card always lands under the reply's **Answer** heading in place of the model's own final line, earlier lines under that heading staying above it as working (`land_answer_card` in `services/answer_fence.py`; physics and chemistry use the same helper, and a STEM reply with no verified result gets the same card without the check, marked `verified: false` so the phone draws no check). A *different* final value in the prose (`x = 7`, one root of two; plain values compared as numbers and sets in `services/answer_check.py`, so `12.75` is not found in `112.75` or `12.755`) gets one line above the heading, "The verified answer is $x = 6$.". Every card the server writes opens with `verified: true` (`services/answer_fence.py`), the only thing the phone draws a green check for; the model's own copy of that line, its "✅ Verified with SymPy" claims, and every spelling of its answer fences (indented, `~~~`, four backticks, `` ``` answer``) are stripped or demoted first, also when the SymPy pool times out; schema-validate otherwise; densify sparse continuous graphs (default ~96 points — enough for a smooth SVG, small enough that a fallback never dumps a wall of coordinates). Written working is appended only for an explanation/steps request and is stripped from answer-only or hint turns. At most a handful of fences of each kind are rewritten so one long reply cannot exhaust the shared 5s SymPy budget. Direct replies run this rewrite in-process (they already carry the fence). A declined solve does not add a couldn't-verify line to the reply. Physics has its own finalizer.

Recurring-pay questions with an amount, a day/week cadence, and a calendar end date use a separate deterministic instant path (`modules/chat/recurring_pay.py`). It reads “today” in the device timezone, counts complete periods and remainder days, lists near-term payment dates, and shows both the today-is-a-payday and daily-proration alternatives. It does not call a chat model or web search.
5. **Mobile** — preprocess delimiters, then render: ordinary inline `$...$` → native `MathText` (KaTeX Computer Modern typography with italic variables and upright digits/operators, tight stacked fractions, continuous scalable SVG radicals that enclose nested fractions, red `\cancel` slash on divide steps); display ` ```math` and heavy answers → **MathJax-SVG** (`MathSvgView` + `lib/math/svgMath.ts`: `mathjax-full` converts LaTeX to SVG lazily behind an LRU cache, rendered via `react-native-svg` — no WebView, no flicker; conversion failure falls back to readable `MathText`); ` ```arithmetic` → a Computer Modern written-work card with fixed place-value cells, carry/regroup annotations, partial products, and a long-division bracket/rows; geometry diagrams → SVG. Native builds render function cards, the expanded graph explorer, number-line solutions, and two-dimensional inequality regions with **Skia**. The expanded explorer (`components/rich/skia/SkiaGraphExplorer.tsx`) adds pinch/pan/double-tap on the UI thread via Reanimated worklets (`lib/math/graphWorklets.ts`). All Skia entry points are lazy and pass through `isSkiaAvailable()`; the SVG canvas remains the Expo Go / stale-client / load-failure fallback. Algebra ` ```answer ` uses the chat-window background, not a gray pill. The answer card and its green check appear only for a fence whose body opens with `verified: true` and only once the reply has settled; any other answer-shaped block (a model's fence, a bare number in an untagged fence, an older saved card) renders as ordinary math. Crash fallback still draws geometry/graph as SVG (not raw JSON).

Camera math is a specialization of step 1: an image with the scanner prompt or another recognized math caption goes through Mathpix when configured, with vision fallback for semantic or uncertain reads, then the supported SymPy extraction path. The vision model's equations, system, inequality or expression are certified only when they are on the page as read (its source text, compared with SymPy): its own setup of a photographed word problem is a reading, as a typed one is. A plain photo with no math caption does not automatically trigger this verified OCR path. Image turns retain the model response path. The scanner reads a math crop back first (`POST /math/scan/read`, `math/api.py`: the same OCR, no solve, 60 reads per user per hour, the global spend cap applies). The student checks or edits the reading and taps **Solve**, which sends it as ordinary text (`Show steps: …`) so the full text pipeline, lessons and word problems included, sees it. **Send photo** sends the image with `I read this as: …` so the turn solves the confirmed reading instead of reading the photo again; it never waits on the read.

**Display math is MathJax-SVG, not a WebView.** `mathjax-full` (tex → svg) loads behind a dynamic `import()` on the first display-math block, and converted formulas sit in an LRU cache (`lib/math/svgMath.ts`), so chat cold start pays nothing. The old KaTeX/MathJax WebView host (`MathFormulaWebView`, `lib/katexRender.ts`, `lib/math/html*.ts`) is deleted; KaTeX remains only as a `features/chat/model/printDocument.ts` dependency and as the native math faces. Native Skia math canvases are likewise lazy (`React.lazy` + `isSkiaAvailable()`), so Expo Go and non-graph chats never bundle or probe them.

### How a formula is drawn

One layout tree (`lib/math/layout.ts`) owns native measurement. Renderers do not invent a second width.

1. **Inline math** — `MathText`. Fractions, radicals, scripts, accents, and cancel marks are native Views. Simple runs stay `Text` so they sit in the paragraph. Variables and Greek use `KaTeX_MathItalic`. Digits, named functions (`sin`, `log`, `lim`), and the operators that face contains use `KaTeX_Main`. `KaTeX_AMS` is only for glyphs that live there (`∴`, `∵`, and `\mathbb` capitals). The UI font is not a math fallback.
2. **Display and heavy inline math** — `MathBlock` → `MathSvgView`. Matrices, cases, aligned environments, and large operators (`\sum`, `\int`, `\lim`, `\binom`) are MathJax SVG drawn with `react-native-svg`, then scrolled horizontally. MathJax keeps scalable brackets. If conversion fails, the same native `MathText` path reads the formula; environments flatten to rows only on that fallback.
3. **Diagrams** — geometry is `react-native-svg`. Function plots, the number line, and inequality regions are Skia (SVG fallback). Tick labels use `KaTeX_Main` from `assets/fonts/KaTeX_Main-Regular.ttf` (the same face `_layout` registers from the katex package; Skia reads a file). Molecule and simulation labels stay on the code face; they are not equations.
4. **SVG** — one radical path (hook, stem, and bar) per root, accent marks that are not a straight rule, and the MathJax display asset. A radical bar is the radicand's ink width plus a short overhang, not the width of the chat bubble.
5. **Measurement** — Computer Modern em advances in `layout.ts`, multiplied by the requested type size. Device `fontScale` scales View boxes and script shifts. `Text` `fontSize` is not multiplied again, because React Native already scales it. Fraction bars, radical bars, and overlines are the measured child ink plus a bounded pad. An unspaced `+` or `=` takes math space as padding on the operator (nested `Text` ignores margin). The characters copy reads stay what was typed. A face is used only when it contains the glyph: digits and almost every relation stay on `KaTeX_Main`; variables and Greek stay on `KaTeX_MathItalic`; `∴`/`∵` and blackboard bold stay on `KaTeX_AMS` (blackboard is the Latin capital in that face, because U+211D is not in the file). `≠` and `∉` are the Main not-glyph drawn over `=` and `∈`. A wide accent spans its ink. A base with both a subscript and a superscript is one column.
6. **Streaming** — an unfinished command, an open group, a trailing `^` or `_`, or an unclosed `\sqrt[` is a placeholder. A complete formula replaces that placeholder. Display fences still wait until the fence closes.
7. **Copy and read-aloud** — `segmentsToPlain` / `readableLatexFallback`. Accents and radicals use combining marks in that string only. The screen draws a measured rule, not the combining mark.
8. **Long formulas** — display SVG scrolls inside the bubble (`maxWidth: 100%`, content at its measured width). Inline math that is stacked, or wider than the window minus a gutter, uses the same scroll. Short inline math stays in the line. Nothing is shrunk to fit.
9. **Regression checks** — `lib/math/__tests__/mathLayout.invariants.test.ts` lays out a corpus of formulas at several type sizes and font scales and asserts box invariants (finite size, radical bar versus radicand, fraction pad, script off the baseline, overline versus ink). Component tests compare rendered style to that same tree.

## Tool-loop path (`MCP_TOOL_LOOP_ENABLED=true`, default)

Heuristic pre-solve and web-search injection **still run**. The model may also call the `sympy` / `web_search` / `calendar` / `generate_image` tools for follow-ups. The math-triggered loop is skipped when `extract_math_intent` is `None` (bare detection without an extractor used to burn the full timeout). Tool results that include a `canonical_fence` / `canonical_answer` in `ToolResult.data` are collected into `VerifiedMathBlock` so post-stream still rewrites or appends fences — but only when the call's equation or expression (and its bounds, limit point, or dimensions, each with its sign) matches what the user wrote, compared with SymPy and read through the LaTeX the keypad types (`math/tool_check.py`); a mistyped call (rhs 19 for `2x + 5 = 17`) stays unverified, and a tool block never replaces a block the server built from the user's text (it may only add a diagram). Direct verified replies skip this loop. Tool **content** is prose + verified numbers, not fence JSON. Plain replies without fences skip the post-stream SymPy rewrite (`needs_math_fence_validate`).

## Worked-solution layout (every subject)

Every verified reply in maths, physics, and chemistry is built by `app/services/workout.py`, and
the model prompts state the same layout (`WORKOUT_PROMPT_RULE`). The sections are **Given**,
**Required** (what is asked; replies before November 2026 say **Find**, and every reader still
takes it), **Formula**, **Substitution** (values into a formula) or **Steps** (an equation changed
one move at a time), and **Answer**, in that order and each only when it has lines. Each line
is one state; its move is a short note after ` — `. A formula rearranged for the unknown is not
a note: a line `Solve for $t$` (`solve_for_line`, one wording wherever a subject writes it:
physics' law rows, maths' slope-intercept form and geometry rearrangements) comes before the
rearranged formula. Chemistry has no such note: a relation it rearranges (Beer–Lambert's
`c = A / (εb)`) opens its Substitution rows. Given is the problem as typed; the solver's
tidy form is its own Expand or Collect line. A both-sides move is shown as the state it
reaches, unless the learner asked why. A rule a trace verifies (product, chain, power,
integration by parts, quadratic formula) is the Formula, named after its dash. The phone renders
each section as a heading with one row per line (`apps/mobile/lib/markdown/workoutSection.ts`).
Do not add a per-feature layout; build a `Workout`.

## Logarithm notation (school convention)

A bare `log` (and `lg`) is base 10, as on a school calculator; `ln` is the natural log; `log_2`,
`log2(…)`, `\log_{b}` and `log(x, b)` keep their written base. The parser
(`solve/parse.py`, its rewrites in `solve/latex_normalize.py`), the symbolic physics grammar,
the phone's graph resampler
(`lib/math/graphExpr.ts`), the extraction prompts, and the chat prompt all agree;
`docs/fixtures/graph_expr_cases.json` holds the resampler to the parser's SymPy values. The
graph fence's `expr` is the parser's reading printed in the resampler's grammar
(`solve/graph_expr_text.py`): `sin x` arrives as `sin(x)`, `|x|` as `abs(x)`, a base-10 log as
`log(x)` and a natural one as `ln(x)`, so the phone resamples exactly the curve SymPy plotted.
SymPy's `log` is natural, so `core/sympy_notation.py` prints it as `\ln` and prints a change of
base `ln(x)/ln(10)` as `\log_{10} x`. An answer that still has a variable stays exact
(`\frac{1}{x \ln 10}`, never `0.434294/x`).

## Formula emit rule (prompts must agree)

- **Answer length:** give the result once with only the key reasoning needed. Short mode keeps prose compact, but never removes an available verified equation/system/inequality trace; “just the answer” is the explicit opt-out. Longer calculus derivations follow explicit requests for steps, explanation, or proof; a hint/practice request should not reveal the full answer. Brevity must preserve domains, branches, units, and constants of integration.
- **Simple roots/powers:** one exact equality chain and an optional approximation are usually enough. Group fractional exponents (`9^{1/6}`); avoid duplicated answer headings and Note/Tip cards that restate the result.
- **Steps / intermediates:** maths numbers each move, in the verified equation lesson and in a reply the model writes itself (`MATH_WORKOUT_PROMPT_RULE` in `services/workout.py`). The number is the instruction (the amount in bold), then the equation with that move written on both sides, then the simplified equation, each on its own line. `4x + 4 = 0` is subtract 4 (`4x + 4 - 4 = 0 - 4`, then `4x = -4`), then divide by 4 (`4x/4 = -4/4`, then `x = -1`). A `Simplify` row is that second line, not its own number. Other subjects keep one state per line with the move as a short note. Inline `$...$` only (no backticks around `$`, no ` ```math` inside a section).
- **Standalone display:** ` ```math` OK for a final equation on its own lines.
- **Diagrams:** Recall attaches ` ```geometry` / ` ```graph` from `canonical_fence`. The model describes the figure in words (`$...$`); it must not emit diagram JSON.
- **Final algebra answer:** Recall attaches ` ```answer ` from `canonical_answer` after the stream. The model writes the result in `$...$`.

## Composer input (mobile)

The stored user text preserves what the composer submitted. Explicit math controls may normalize that text before submission; OCR and solver context augment the model input separately:

- **Symbol toolbar** (`MathKeyboardBar` / `mathKeyboardSymbols.ts`) inserts LaTeX snippets (`$...$` when the caret is outside math). A key types into the box the caret is in; ← → (`lib/math/caretStops.ts`) move between boxes. The server reads what the keys type: `^{-1}` after a function name is the inverse (`\cot^{-1}` → `acot`), `\mathrm{i}` is the imaginary unit (so is a typed `i` in an expression of numbers and `i` alone, as in `i^23` or `(1 + i)/(1 - i)`; beside other letters it stays a variable), and `modules/math/tools/keyboard_notation.py` rewrites `\int_{a}^{b}…\,dx`, `\frac{d}{dx}`, `\binom`, and `^{\circ}` into the notation the extractors read.
- **Ordinary typing and native paste** preserve the exact input and native caret. Autocorrect and spellcheck stay disabled so notation such as `sqrt` and assignment expressions cannot be rewritten while typing.
- **Explicit math keypad / Paste controls** opt into formatted math editing. `mathPasteNormalize.ts` maps pasted Unicode math glyphs to LaTeX (the same glyph set spirit as `_UNICODE_OP_SUBS` in `math/solve/unicode_normalize.py`). The in-app Paste button reads clipboard text only; it does not import an image. Use Scan Math or a photo attachment for image input.
- **Scan Math** captures a camera frame or imports a photo. Imported photos fit inside the preview so the initial crop contains the full image; camera previews retain their fill/crop behavior. For math, physics, and chemistry, Solve crops and opens **I read this as** (`features/scanner/components/ScanReadingReview.tsx`): the reading arrives in an editable field, **Solve** sends the checked text, **Send photo** sends the crop at once without waiting, and **Retake** returns to the camera. Biology still sends the crop immediately, with no read-back.
- Backslashes, `_`, and `*` inside math are protected during Markdown preprocessing and restored at the native/MathJax-SVG parser boundary, so Markdown cannot consume math escapes or reinterpret subscripts/multiplication as emphasis.

## Key files

| Layer | Path |
|-------|------|
| Neutral subject dispatch | `apps/api/app/services/subjects/dispatch.py` (each subject's adapter registered in `services/subjects/registry.py`), `services/solving.py` |
| SymPy core | `apps/api/app/modules/math/solve/` |
| Triangle laws | `apps/api/app/modules/math/solve/triangle.py`: cosine and sine rules, Heron's formula, validity; exact where SymPy has the cosine (30°, 45°, 60° and their supplements) |
| Physics (peer subject) | `apps/api/app/modules/physics/` — `catalog/`, `extractors/`, `solvers/`, plus `extract.py`, `solver.py`, `direct.py`, `block.py` |
| Pre-stream inject | `apps/api/app/modules/math/tools/` |
| Whole-request integrity | `apps/api/app/modules/math/request_consumption.py` |
| Post-stream fences | `apps/api/app/modules/math/fence.py` |
| Camera OCR | `apps/api/app/modules/math/ocr.py`, `apps/api/app/modules/math/image_extract.py`; read-back `apps/api/app/modules/math/api.py` |
| Step traces | `apps/api/app/modules/math/solve/key_steps.py` (equations), `traces.py` (inequalities, 2×2 systems), `derivative_steps.py`, `integral_steps.py` |
| Written arithmetic | `apps/api/app/modules/math/solve/written_arithmetic.py`, `written_division.py`, `modules/math/schemas/arithmetic.py`; mobile `components/rich/ArithmeticWorkBlock.tsx` |
| Fraction procedures | `apps/api/app/modules/math/tools/extractors/fractions.py`, `solve/fractions.py`, `modules/math/schemas/fraction.py` |
| Check my work | `apps/api/app/modules/math/tools/work_request.py` (reading the lines), `solve/work_check.py` + `work_lines.py` + `work_slips.py` (grading and slips), `tools/block/work.py` (reply) |
| Word problems | `apps/api/app/modules/math/tools/word_problem.py` (gate, number guard, structured call), `tools/word_templates.py` (textbook shapes read without a call), `solve/word_problem.py`, `tools/block/word.py`, `modules/math/schemas/word_problem.py` |
| Recurring pay + date arithmetic | `apps/api/app/modules/chat/recurring_pay.py`, hooked before prompt/model work in `modules/chat/turn_prep/instant.py` |
| MCP sympy | `apps/api/app/modules/math/tool.py` |
| Prompt hints | `apps/api/app/modules/math/reply_policy.py` (the maths pack and reply policy; chat lists it in `modules/chat/prompt_subjects.py`) |
| Mobile preprocess | `apps/mobile/lib/markdown/markdownPreprocess.ts`, `apps/mobile/lib/math/normalizeImplicit.ts` |
| Composer math input | `apps/mobile/lib/math/pasteNormalize.ts`, `keyboardSymbols.ts`, `features/chat/components/MathKeyboardBar.tsx` |
| Render | `MathText`, `MathView` / `MathSvgView` (MathJax-SVG), `GeometryBlock`, `FunctionGraphBlock` + `rich/skia/` graph, number-line, and inequality canvases |

## Curriculum coverage (K–12 through undergrad homework)

The factual grade-by-grade audit is [MATH_GRADE_1_12_COVERAGE.md](./MATH_GRADE_1_12_COVERAGE.md).
It distinguishes **VERIFIED**, **VERIFIED + PROCEDURE**, **TEACH**, **LLM-ONLY**, and
**MISSING**. Do not treat the capability index below as a claim of complete curriculum coverage.

The LLM can **talk** about almost any homework. **Verified** work (pre-stream SymPy + canonical fences) covers the `MathIntent.kind` list in [`math/schemas/intent.py`](../apps/api/app/modules/math/schemas/intent.py) (**34 kinds**). Physics has a separate, disjoint `PhysicsIntent` and a peer pipeline; it is described only for cross-reference below, not registered through math. Anything else is unverified prose. That is intentional: the app renders; the server verifies only what a complete extractor and deterministic solver can close. Proof-based analysis and abstract algebra stay LLM-only. Count kinds from the schema Literal, not from this table.

[`math/tools/`](../apps/api/app/modules/math/tools/) is the feature split: ordered `_INTENT_EXTRACTORS` in `extract.py` plus `kind → _verified_block_*` in `block/`. Do **not** add a second kind table. Extraction also records what the question asked (`MathIntent.geometry_request`, `MathIntent.plot_point`); the block copies it and direct replies read it, never the question: a geometry working is looked up by `(shape, quantity)` in `direct_geometry_working/`, and a literal point plot skips the model only for the request it was read from. Rendering: inline `MathText`, display math MathJax-SVG (`MathSvgView`), geometry diagrams `react-native-svg`, and native math graph surfaces Skia (`rich/skia/`, with SVG fallback).

Camera OCR is a **subset** of the kinds below (no square / trapezoid / matrix / series / Newton / solid).

### Verified today

| Band | Covered as verified | How |
|------|---------------------|-----|
| Arithmetic (1–6) | Bare digits+ops when `bare_arithmetic_expr` agrees (`7*8`, `8-8*2`, cued `what is 9/9`). Standalone subtraction such as `2-6` is verified. Lone-slash input (`9/9`) still needs a compute cue; phone/date shapes and ranges in prose stay outside this shortcut. For two non-negative literals, server-owned school methods cover vertical addition/carrying, subtraction/regrouping across zero, multiplication carries/partial products, long division/remainders, and terminating decimal versions. Equations (`1/2+1/3 = x`) and simplify/factor too. A number written in groups of three (`1,200`) is one number unless the message is a comma list typed without spaces. `a x 10^n` is scientific notation, never the unknown x, however the power is typed (`1.8·10⁻⁵`, `1.8 \times 10^{-5}`), and stays an exact product for SymPy. A spaced `x` between two numbers is times (`456 x 23`); a glued `8x5` stays a dimension and `2x + 3` stays algebra. Spoken operators read inside a longer sum (`3 times 4 plus 2`, `1.8 x 10^-5 times 2`), as do the chat spelling `wat is`, `log base 2 of 64` and `1234 ÷ 7 with remainder` (the card says `176 R2`). `5/0`, `0/0`, `log 0` and `tan 90°` are verified as undefined, and no card ever shows NaN or complex infinity. | `arithmetic` with `school_op`, `_extract_equation_intent`, calculus `simplify` |
| Teaching pictures | Closed requests for place value, number bonds, ten frames, equal-group arrays, fraction bars and a fraction number line, integer jumps that start negative, decimal comparison, half-up rounding to a named place, polynomial and synthetic division, the unit circle at a standard angle, quartile box plots, frequency tables, stem-and-leaf plots, short integer histograms, stated scatter points, fair coin and die trees, and point translation, reflection, rotation, and dilation. The picture reuses the arithmetic fence. The answer chip stays the verified value. Answer-only turns omit the picture. | `arithmetic` `teaching_op` |
| Pre-algebra | Fractions/exponents in equations; gcd/lcm/primes/mod. Roots in words, typed as chat (`wats the squre root of 225`), and an odd root of a negative whole number (`cube root of -27`; an even one stays with the model). A terminating decimal as a fraction (`0.375` → `3/8`). How many factors a whole number has, with its factor pairs. Fractions: `divide 3/4 by 2/9`, `half of 3/4`. | `equation`, `number_theory`, `arithmetic` (`school/number_facts.py`, `extractors/fractions.py`) |
| Algebra I–II | One equation, systems (≤4), inequalities + number-line intervals; affine two-variable shaded half-planes. **Lessons** from verified `key_steps` for linear / pure-power / quadratic equations, linear and compound inequalities, and 2×2 linear systems (substitution or elimination) when Detailed, “show steps”, or Balanced with 2+ ops. A side already solved (`x = 6`, `x = 3, y = 1`) is never solved again: that certified whatever was typed. A system typed with no verb (`x+y+z=6, 2x-y+z=3, x+2y-z=2`, `3x+2y=12 and x-y=1`) is two to four equations and nothing else, one with a term, so a list of assignments (`a=1, b=2`) is not one. A misspelled leading `slove` is `solve`. `zeros of f(x) = x^2 - 4x` solves the formula, not `f(x) = …`. The remainder of polynomial division (`the remainder when x^3 + 2x - 5 is divided by x - 2`) is checked as P = QD + R and, for a divisor x − a, shown as P(a). **Features of one equation** (`school/equation_features/`: `extract.py` reads the request, `solvers.py` works it): the vertex and axis of symmetry of `y = ax^2 + bx + c`, the y- and x-intercepts, the discriminant, the sum and product of the roots, the parameter that gives one / two / no real roots, a line's slope and slope-intercept form, and the line through a point parallel or perpendicular to a line; the period and amplitude of `y = A sin(Bx + C) + D` (or cos; a tangent's period is left to the model, and it has no amplitude); how many solutions one polynomial equation has (`how many real roots does x^2 + 2x + 5 = 0 have`), where without "real" the count must be the same over the reals and the complex numbers. The request audit refuses to solve an equation for x when a feature was asked, so a feature these rules decline stays with the model. | `equation`, `system`, `inequality` + `number_line` / `inequality` graph |
| Checking work | The student's own lines in one unknown, polynomial sides of degree ≤ 2: each line is right when it has line 1's solutions. The first wrong line is named with its slip (sign lost moving a term, one side only, multiplying where dividing undoes, inequality not reversed or reversed for no reason, sides swapped, bracket half-expanded or sign slip, like terms, dividing some terms, a root lost or a factor's root sign, an answer that fails substitution); every proposed fix is itself verified. A later line is graded against line 1 too, so a right final answer after a slip gets its ✓ and the slip is still named. Hint mode keeps the fix back, and fully right work in hint mode is told it is right. A typed answer in a thread (`check my answer: x = 6`, a bare `x = 6`) is checked as a two-line work check against the open problem (the equation the assistant offered, else the user's last equation); with no single open problem it stays with the model. | `work_check` |
| Word problems (algebra) | Four textbook shapes, read by the server's own templates: consecutive (odd or even) integers with a stated sum, two ages with a difference and a sum, tickets at two prices with a count and a total, and mixing two strengths to a target strength. Other ages, sums and differences, tickets and prices, and perimeter-style setups (up to 3 unknowns and 4 equations) are translated by one structured call and solved when every number is stated and exactly one solution fits the domain, but that translation is the model's reading: the model gets it as an unchecked setup, never as a verified card. The templates need no call: consecutive (odd or even) integers with a stated sum, two ages with a difference and a sum, tickets at two prices with a count and a total, and mixing two strengths to a target strength. `tools/word_templates.py` reads the whole message and writes the same setup the translator would, which then passes the same grounding check and SymPy solve; a parity, a whole count or a target strength the numbers cannot give is declined to the translator. | `word_problem` |
| Geometry (2D) | Rectangle, square, triangle (base/height), right triangle, SSS, trap, para, circle, sector | geometry fences |
| Geometry (3D) | Cube, rectangular prism, cylinder, cone, sphere, pyramid (volume / surface area). Numbers only — no 3D SVG fence. | `solid` |
| School templates | `15% of 80`, `10% of 10% of 500`, `25% of 80 plus 10` (anything more after the base, such as `plus tax of 8%`, is declined); increase/decrease/markup by `%`; `what percent of`; percent change from A to B; discount / `with tax`; simplify `6:8`; split a total in `a:b`; AP/GP nth term and first-N sum; infinite GP (`\|r\|<1`); annual simple/compound interest and present value (also `$5000 invested at 4% interest compounded annually for 3 years, how much will I have`, which is the amount; another compounding period, or the total of simple interest, is declined); change from a payment (`I bought 3 notebooks at $2.40 each and a pen for $1.85. I paid with a $20 bill`, exact decimals; `3 notebooks for $2.40` could be the price of one or all and is declined); union/intersection/difference of two `{…}` sets; work-together (two hour-times); two-part `%` mixture; `twice as many` + together + one total; unit rate; three-number direct/inverse proportion; rounding to decimal places or sig figs (a 5 rounds up: 2.675 to two places is 2.68; `services/school_rounding.py`); `how many seconds in a day` between units of one fixed size (a month or a year is not one) | `arithmetic` (`school.py`), `unit` |
| Trig (evaluate / equations) | `sin(30°)` etc. Equations like `sin(x)=1/2` return every real periodic branch with an integer parameter. Unsupported explicit domains and unresolved solution sets stay on the model path. Identities (`show that` / `prove that` / `identity`) certify only when lhs−rhs is identically 0. AAA triangles use law of sines with explicitly relative lengths; physical area/perimeter needs a side length. | `trig`, `equation`, `triangle_sides`, calculus `identity` |
| Coordinate geometry | Distance, midpoint, slope; line through two points; distance from a point to `ax+by+c=0` | `coord` |
| Vectors | Magnitude, unit vector, angle, projection, dot, cross. Round brackets are vectors for an angle only when the request says `vectors`; as points the question has no answer. | `vector` |
| Functions | Domain and range on the maximal real line; inverse when single-valued, including one SymPy returns under a condition on its values (`e^x` → `ln x`, `(2x+1)/(x-3)` → `(3x+1)/(x-2)`; `x^2` keeps two branches and is refused); `f(g(x))` composition; even/odd (or symmetry about the y-axis / origin). A restriction such as `on x ≥ 0` is **refused**, not peeled. | `calculus` (`function_domain` / `function_range` / `function_inverse` / `function_compose` / `function_symmetry`) |
| Linear algebra | 2×2–4×4 det, inverse, multiply, add, transpose, rref, eigenvalues, eigenvectors, diagonalize, rank, nullspace, column space, row space (`[[…]]` bracket notation only; `det [[2,3],[1,4]]` is the determinant). Singular inverses and non-diagonalizable matrices cannot become numeric answers. | `matrix` |
| Calc I–II | simplify, factor, expand, d/dx (lesson rule by rule: sum, constant multiple, power, product, quotient, chain, exponential, standard functions), ∫ (+C; lesson by method: power rule, standard forms, u-substitution, integration by parts), definite ∫, limits (one-sided; two sides that both have a limit and disagree are a verified "does not exist", and a limit SymPy only bounds, such as `sin(1/x)` at 0, is declined), series sum (do not certify oscillating divergent series), Newton; Taylor/Maclaurin, partials, gradient/div/curl of an explicit formula, directional derivative, linear approximation, average value, implicit `dy/dx`, first-order `dsolve`, 2nd/3rd derivative, double/triple integrals over named axis-aligned boxes. Spellings read: `factorise`/`factorize` and misspelled `derivitive`/`intergrate`; the `∫` sign is the verb (`∫ (3x^2 + 2x) dx`, `∫_0^π sin x dx`); LaTeX typed without `$` (`\frac{d}{dx} x^5`); `limit as x approaches 2 of …`, `lim x→∞ …`, `lim … as n->infinity`; `sum k^2 for k=1 to 10`; `by parts` as the method, not the integrand. `factor 360` is its prime factorization (SymPy's `factor` used to certify 360). **Applications:** area between two explicit curves on an explicit interval, arc length, volume of revolution about a named axis. Written proofs stay LLM. | `calculus`, `limit`, `series`, `numerical_method` |
| Probability | Binomial / geometric / Poisson PMF, complement, Bayes with three probabilities, expected value of a list (and of one fair die), exact conditional sample spaces for two fair dice with a stated sum condition, at least one head or six in n fair trials, and draws from a bag of colours when every draw is one colour (`school/bag_draws.py`). Whether the marbles go back is never assumed: the question must say with or without replacement (or at the same time), and any other event (one of each, the first red and the second blue) stays with the model. | `probability` |
| Complex / units | Simplify `a+bi`; modulus / argument / conjugate / polar form; Pint unit convert (SI case-sensitive symbols) | `complex`, `unit` |
| Graphs | y=f(x), two curves, vertical line, point, axis-aligned ellipse, polar `r=f(θ)`, parametric `x(t), y(t)`. `f(x)=0` with no y is a plot of lhs−rhs (a parabola), not two vertical lines. Direct verified plots skip the LLM. `graph it` replots the last plottable request in the thread, including the lines a derivative or system question names; with none, the model asks which function and never draws a text sketch; a sketch in characters that slips through is removed after the stream (`math/text_plot.py`). Sampled segments split at SymPy-detected poles confirmed diverging by the samples (even-order poles like `1/x²` included); non-decidable cases keep the numeric sign-flip heuristic. | `graph` / `graph_pair` |
| Stats (descriptive + bivariate) | mean, median, mode, variance, stdev, range, quartiles, IQR, percentile. Correlation, covariance (sample/population), linear regression — only with two explicit equal-length lists. Weighted data cannot silently become a different calculation. | `statistics` |
| Discrete (intro) | n!, nCr, nPr; gcd/lcm of two to ten numbers (`hcf`, `gcf`, `highest common factor`, `lowest common multiple`)/primes/mod; modular inverse, totient, two-congruence CRT; arrangements of a word whose letters all differ (`how many 4 letter arrangements of the word MATH`; a repeated letter is declined) | `combinatorics`, `number_theory` |

**Physics is a peer subsystem.** Its verified kinds, direct presentation, units, and trajectory/simulation rules are owned and tested under `modules/physics/`; see [physics.md](./physics.md), [SUBJECT_SEPARATION_TICKETS.md](./SUBJECT_SEPARATION_TICKETS.md) and [FEATURES.md](../FEATURES.md) §4.

```mermaid
flowchart TB
  ask[User homework]
  subject{Neutral subject detection}
  math[Math extractor registry]
  physics[Physics extractor registry]
  audit{Whole request consumed?}
  llmx[LLM extract fallback — bounded, flag-gated]
  sympy[Math solver + typed trace]
  physolve[Physics solver + working]
  llm[LLM only unverified]
  ask --> subject
  subject -->|math| math
  subject -->|physics| physics
  subject -->|none| llm
  math --> audit
  audit -->|complete| sympy
  audit -->|meaningful leftovers| llm
  math -->|no kind| llmx
  llmx -->|complete candidate intent| sympy
  llmx -->|found=false / timeout| llm
  physics -->|complete intent| physolve
  physics -->|unsupported / partial| llm
```

### School-homework gaps (unverified LLM)

Still not a verified kind (the model may answer; it must **not** claim a verified result). Closed formula templates on existing kinds are verified. Concept-only nodes (counting objects, axioms, “meaning of a fraction”) are not a solver kind.

1. **Open-ended word problems** are never verified: the structured translation that closes is shown to the model as an unchecked setup (see the table), and a translation with an unstated number, no unique solution in the domain, or more than 3 unknowns stays LLM-only, as do proofs and multi-step stories that are not one system of equations. Only the four template shapes are certified.
2. **Written proofs** — an identity equality is not a proof. Induction, contradiction, and prose proofs stay unverified. **Angle-only triangles** (AAA summing to 180°) are verified via the law of sines with explicit `relative_lengths` provenance. Their diagrams omit a physical area; a measured side is required to determine area or perimeter. SSS still uses law of cosines for angles-from-sides.
3. **Unit-symbol casing** — Pint already covers energy/force/pressure/etc. Symbols that need uppercase (`J`, `N`, `Pa`) must be passed through with original case (lowercasing before lookup used to drop them). `fl-oz` aliases to Pint `fluid_ounce`.
4. **Physics requests** — are not math coverage. They use the independent physics extractor,
   solver, prompt, direct-reply, and fence path; its own unsupported cases remain unverified.

New verified math homework lands as one `MathIntent.kind` plus a math extractor, math builder,
solver, and tests. New physics homework uses the equivalent physics-owned registry. Neither
subject adds a branch to the other's registry. `math/tools` is a package (`extract.py` registry,
`block/` builders, `school.py` extra kinds) — do not add a second math kind table.

### Adding a verified operation

Each step has one home; nothing else needs an edit.

- **A new operation of an existing kind** (a statistic, a matrix operation, a solid, a
  fraction procedure): add its name to the kind's `Literal` in `schemas/operations.py`, which
  `MathIntent`, the solver inputs and the matchers all read; then teach the matcher
  (`match/discrete.py`, `match/geometry.py`) the words and the solver (`solve/`) the
  operation.
- **A school operation** (a percent, interest, ratio or rounding shape on `arithmetic`,
  `coord`, `vector`, `probability`, `complex`, `unit` or `trig`): put its reader and its block
  side by side in `tools/school/<topic>.py`. A new reader goes into `SCHOOL_EXTRACTORS`
  (`tools/school/__init__.py`) at the place its order comment allows; a new school kind's
  block goes into `SCHOOL_BLOCK_BUILDERS`.
- **A new kind**: add it to `MathIntent.kind` (`schemas/intent.py`), its extractor to the
  ordered `_INTENT_EXTRACTORS` in `tools/extract.py` (the order is the behavior; say in a
  comment why it sits where it does), its builder to `_BLOCK_BUILDERS` in
  `tools/block/__init__.py`, and its SymPy work to `solve/`. A declined SymPy step goes
  through `solve/declines.py` (`@declines` or `sympy_decline()`), never a bare `except`.
- **Tests**: `test_math_catalog_all_kinds.py` needs one verified end-to-end example of every
  kind; add the question, its look-alikes and a decline to `stem_corpus/math/` and any
  everyday look-alike to `sweep_corpus/math_lookalikes.json`.

## When no verified result stands behind the reply

Maths, physics and chemistry share one contract for a reply the model works out itself
(`services/workout.py`):
- **Layout:** one renderer for every worked answer. Told the layout in words, the model
  followed it on one turn and not the next (bold inline "**Given:** …", no Answer heading, no
  card). A calculation nothing verified now asks for its parts instead: the model writes a
  ` ```worked ` block of records, one per line (`given: v | 20 | m/s | speed`, `required`,
  `formula`, `solve_for`, `step`, `substitution`, `answer`, `part`;
  `modules/chat/prompt_constants/worked.py`). Each record is validated with Pydantic
  (`modules/chat/worked_solution.py`) and the server lays the solution out with
  `render_workout`, the renderer of every verified reply (`modules/chat/worked_render.py`;
  physics heads the formula with the law's name and cards the value alone, as its verified
  replies do). The layout streams: `modules/chat/worked_stream.py` sits beside the scaffold
  filter and puts out each section as its records arrive, never the records themselves.
  A model that writes no block gets today's reply; a block with no valid record is shown as
  written. Which turns ask for it: `modules/chat/worked_turn.py` (nothing verified, a number
  in the message, and a maths, physics or chemistry subject, a school exercise or a science
  question; `worked_layout_enabled`). Headings stay English for every locale, as a verified
  reply's do; the names, meanings and moves are in the reply's language.
- **Not checked:** the value under **Answer** goes in the same card a verified one does,
  marked `verified: false` (`land_answer_card`); the phone draws it in a dashed box with no
  check and no label (`components/rich/AnswerBlock.tsx`; the "Not checked" tag was removed in
  November 2026).
- **Headings:** every worked layout reads Given, Required, **Solution** (a heading alone),
  then the formula under its own name and "formula" (**Average speed formula**; a name that
  already ends in law, theorem, rule, principle or equation stays: **Ohm's law**), never the
  name as a note beside the formula (`services/workout.py`, `formula_heading`).
- **Self-check:** `SELF_CHECK_PROMPT_RULE` tells it to check the result before **Answer**: put it
  back into the formula, redo each multiplication, and check the units and size. It may add a
  one-line **Check**, never a ✓.

The server then recomputes the working (`modules/chat/working_check.py`):
- **What it checks:** every `$...$` equality whose two sides are plain numbers once units are
  dropped, on unverified STEM turns and on any worked solution.
- **What it reports:** the first step off by more than its rounding and 1% gets one line under
  the reply, "Check this step: $3.2 \times 4.5 = 14.4$, not $14.8$."
- **What it leaves alone:** variables, unit conversions, prefix steps (≈ 4.5 MJ), percents and
  degrees.
- **Measured:** on 5,896 corpus replies it raised no false alarm, and it caught every slip
  injected into server-written working.

## STEM sweep

`apps/api/app/tests/behavior/stem_corpus/math/` holds 458 turns: the 432 from the September
investigation (homework questions with answers worked independently, "find the X of …" traps,
notation spellings, follow-ups, questions that must be declined, and everyday look-alikes) and
the look-alikes added with each widened rule. Each runs
through the real chat path. `stem_math_judge.py` reads the answer card with SymPy alone (no
solver code) and compares it with the worked answer: a number to 0.5%, an expression exactly,
an antiderivative up to a constant, an inequality or interval as the same set. `test_stem_sweep.py`
fails on a wrong verified answer or a misread turn and holds every answered entry by name
(`stem_snapshot.json`, 390 of 413). The judge also reads the school remainder `176 R2` and a
dollar card `\$10.95`.

    uv run python -m app.tests.behavior.stem_sweep math --show

## Failure classes closed by the systemic procedure pass

| Exposed case | Root cause | General fix and regression family |
|---|---|---|
| `sin(30°)+cos(60°)` certified only the first term | A single-call extractor accepted a prefix without proving full consumption | Complete-expression trig extraction plus call-count consumption checks; degree/π, spacing, wrapper, and extra-clause traps. Bare numeric angles remain ambiguous and unverified. |
| A second operation/statistic/measurement was silently ignored | Extractors had no final semantic-leftover seam | `ConsumptionAudit` rejects additional operations and unsupported multi-stat requests; supported multipart geometry retains every requested flag/value atomically. |
| Physical speed/rate questions entered math | Physics cues and an average-speed extractor were registered through math | Neutral subject selection plus physics-owned rate extractor/solver/unit tests. |
| Carrying, borrowing, or long-division work could differ from the answer | The model was asked to recreate school working | Typed arithmetic columns/cycles are generated by the server and rendered verbatim; property tests check sum, difference, partial-product, quotient, and remainder invariants. |
| Decimal work lost alignment or placeholder zeros | Presentation reconstructed values from numeric output | Exact operand strings and decimal positions are retained in the arithmetic trace. |
| Fraction answers lacked a reliable school procedure | General expression solving had no fraction operation model | Closed fraction grammar, exact-rational solver, and typed `FractionWorkSpec`; property tests verify rational equivalence. |
| `x^0` disappeared from a worked equation without naming the law | Simplification happened before the teaching trace | A verified zero-exponent-law step is prepended, including the nonzero-base condition. |
| Fractions, radicals, signs, or lowercase variables changed in presentation | Render layers inferred structure from already-formatted text | Source-preserving preprocessing and native math render regressions cover fractions, radicals, negative signs, exponents, lowercase identifiers, answer-card layout, reopen, and user-message paths. |
| A feature of an equation (vertex, intercept, discriminant, "find k so that … has one solution") was answered by solving the equation for x | The equation extractor took any leading `find`/`what is` as a solve cue | Feature rules answer the asked quantity; `request_consumption` refuses an equation or system solve when a feature word or a solution-count condition is present. |
| A student's own answer (`x = 6`) came back as a verified card | A side already solved was solved again | Already-solved sides and lists of values are not extracted; in a thread the claim is a work check against the open problem. |
| "simplify it" was the product `i t`; "differentiate between weather and climate" got the maths prompt | A pronoun parsed as two letters; a calculus verb counted as maths with no object | `math_expr_or_none` refuses a bare pronoun; the gate needs a maths object after the verb; in a thread "it" is the user's last expression, and only after an operation that keeps its value (after "derivative of x^3" it could be either, so it stays with the model). |
| Everyday spellings (`456 x 23`, `factorise`, `lcm of 12, 18 and 30`, `det [[…]]`, `∫ … dx`, a system with no `solve`) got no maths instructions, and `∫ (3x^2 + 2x) dx` kept the sign inside the integrand | Each grammar knew one spelling, so the gate, the extractor and the direct-reply guard disagreed | The spelling is taught to the grammar that owns it, so all three read the same words (`times_between_numbers`, `CALC_OP_SPELLINGS`, `parse_limit`, `bare_equation_system`, …); `x` is times only when spaced between two numbers; every widened rule adds its look-alikes to `sweep_corpus/math_lookalikes.json` and the maths corpus. |
| `factor 360` verified 360, and an interest question asking "how much will I have" could get the interest | The extractor answered the operation it recognised, not the quantity asked | Calculus declines factoring a bare integer, which number theory reads as its prime factors; the interest template reads the question and declines a total it does not model. |
| `20% of 1,000` was 0.2 and `25% of 80 plus 10` was 20 | The base stopped at the thousands comma; the rest of the sentence was dropped | Digit groups fold before extraction; the percent grammar reads the whole request or declines. |
| `limit of sin(1/x) as x->0` was verified as the interval `⟨-1, 1⟩`; through the `sympy` tool `(-1)^n` reached a card as NaN and `1/n` from `n = 0` as `\tilde{\infty}`; an average value over `[0, ∞)` was 0 | The solvers passed on whatever SymPy returned: accumulation bounds, NaN, complex infinity, an unevaluated `Limit` or `Integral`, a complex value | `compute_limit` returns a real number, `±∞`, or complex infinity only for a two-sided limit at a point whose one-sided limits both exist and differ (the verified "does not exist"); anything else is declined, for the block and the tool alike. Accumulation bounds are no proof the limit is missing: `sin²(1/x) + cos²(1/x)` gets `⟨0, 2⟩`, though it is 1. A sum with an undefined term, and an average value over an infinite interval or of an integral without a finite value, are declined too. |
| "1.200 + 800" from a Spanish user was a checked 801.2, and a French physics question a checked answer to the half it read | The readers are English grammars that read numbers the English way; in another language they read the numbers and skip the words | `turn_reading/readable.py` reads another language on positive evidence (another script, or words only the app's other languages write) and a number its writer's locale reads otherwise (a dot grouping thousands, a decimal comma, groups set apart by a space); `chat/whole_question.py` drops the verified result whole, card, picture and instant reply. |
| "Find the cube root of 27a^3 + 54a^2b + …" got a checked card that was the question: the model reader wrote `cube_root(…)`, parsed as one symbol times the polynomial, which "simplified" to itself | The parser turned any unknown name into a symbol or into its letters, and nothing held a card to the expression it came from | `solve/written_names.reject_unknown_names` declines a name that is not a function or constant SymPy knows, a Greek letter, a subscripted letter, a declared name, or one-letter variables written together (`3abc`, `lwh`, `abcd` in order; a letter twice, `cube`, `fog(x)` are words). `solve/restated.card_restates` compares a simplification's, factorisation's or expansion's card with the expression it was given, as SymPy trees parsed as written: a root of that very sum, not taken (`\sqrt[3]{27a^3 + …}` for the reader's (27a^3 + …)^(1/3)), is no answer, from the readers or the `sympy` tool. A card equal to an expression with no root left on it is one ("simplify (x+1)/(x-1)" is already simplest, its excluded value beside it), and `1/(x - 1)` for "(x+1)/(x-1) - x/(x-1)" is never matched inside the question. A number, one letter or an equation is never a restatement. |
| A model-authored answer or visual could conflict with a verified result | Canonical replacement and subject ownership were mixed in the math fence | Subject-specific finalizers replace or append canonical data; the neutral stream dispatches by `VerifiedMathBlock`/`VerifiedPhysicsBlock`. |

## Math quality review — September 12, 2026

This pass checked the path from user notation through extraction and verified answers, plus native rendering and streaming. It is **not** the coverage inventory — that is the table above. `test_math_catalog_all_kinds.py` enforces one verified end-to-end example for every declared `MathIntent.kind`; the deeper regression matrices live in `test_math_category_regressions.py` and `test_math_review_geometry_calculus.py`. These tests use no model calls.

| Part | Representative checks and corrections |
|------|----------------------------------------|
| Arithmetic, fractions, roots, powers | Order of operations, percentages, sixth root of 9, nested radicals, grouping a fraction under division/powers, negative substitution, decimal ratios. |
| Algebra | Linear and quadratic equations, both roots, systems; readable fractions and fractional exponents. |
| Trigonometry | Preserve the entire argument and explicit radians. Reject extraction that would drop a leading multiplier or second trig term. |
| Calculus | Respect the requested variable/differential; include `+ C` for indefinite integrals; preserve one-sided limit direction; distinguish a nonexistent two-sided limit from positive infinity; do not certify an unevaluated or oscillating divergent series as a sum. |
| Geometry | Canonical area/perimeter/diagonal matches the requested quantity for supported shapes. Base and height alone cannot certify a general triangle or trapezoid perimeter. |
| Statistics and probability | Fractions and scientific notation remain whole data values; sample/population variance, binomial probability, raw-list expected value. Weighted data and fractional discrete parameters cannot silently become a different calculation. |
| Discrete and matrices | Factorial, combinations, integer number theory, exact determinant/inverse; singular inverses and invalid counts cannot become numeric answers. Arithmetic with factorials (`6!/4!`) writes the expression once with its values (`6!/4! = 720/24`) and puts the result alone in the answer; a quotient of large factorials cancels (`100!/98! = 100 × 99`). |
| Graphs | Preserve the direct verified function-graph path and its existing regression coverage. |
| Rendering | Callout math uses the same notation parser; complete streamed formulas keep their escapes; unfinished explicit math is held until renderable. Fractional powers and root indices are readable; stacked fraction bars group their contents without invented parentheses. Heavy calculus/matrix notation gets a full-width typesetting host. Multi-branch native answers retain each branch and its parameter conditions in bounded horizontal scroll hosts. |

The verified extractor is deliberately narrower than general mathematical language. Combined/prefixed trig expressions, weighted expectations/statistics, some natural-language geometry forms, and the school-homework gaps above still use the language-model path. Bare numeric trig shorthand such as `sin(30)` retains the existing degrees convention; specify radians explicitly when intended. The separate Vite web client does not yet have parity with the mobile math renderer.

Prompt tests verify that brevity and formatting instructions reach the model; they do not establish how every live provider will follow those instructions. Visual verification used the iOS simulator with representative formulas, not an exhaustive proof of every possible LaTeX expression or an Android device run.
