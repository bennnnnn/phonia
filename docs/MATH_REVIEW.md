# Math review — 2026-10-12

Scope: the worked-solution ("workout") format, who solves what (SymPy or a model, and which
model), code structure, test and curriculum coverage, geometry drawing and Skia, and the
scanner. The goal is for Recall to be the app students reach for in maths, physics, and
chemistry, with biology and economics to follow.

Method: about 120 prompts run through the real pre-stream path
(`build_subject_augmentation` → `maybe_direct_subject_reply`, real SymPy, model calls off),
the math suite run with coverage, and the mobile renderers read. Commands are at the end.

## Verdict

1. **The engine is strong where it engages.** The suite has 3,525 math tests and 88% line
   coverage, and every line of the equation, inequality, system, derivative, integral,
   written-arithmetic, and check-my-work traces is checked by SymPy.
2. **It sometimes engages wrongly.** Seven inputs return a wrong answer as a direct "verified"
   reply, with no model involved (§2). These are P0.
3. **There is no single workout format.** The server has nine layouts, plus whatever the model
   writes. They are verbose: a bold heading on every step, "Simplify" rows, and Given / Find /
   Formula / Substitution / Answer headings with a blank line after each value. §3 describes the one
   layout that now replaces them.
4. **Reach is the bottleneck, not solving.** One in three everyday phrasings never enters the
   math pipeline ("factorise", "hcf", "x squared minus 5x plus 6 equals 0").
5. **Geometry is not on Skia.** It is eight fixed SVG templates. Five of the 18 "verified
   teaching pictures" are drawn as a sentence.
6. **The scanner can silently drop a term** from what it shows the student as "I read this as".

The biggest lever is strategic. Today a verified workout exists only when a regex grammar
closes the request. Let the model draft the workout in the compact grammar, and let SymPy audit
every line with the check-my-work engine that already exists. Coverage then grows with the
model, not with the regex tables (Phase 2).

## Status — fixes shipped on 2026-10-12

| Item | State |
|---|---|
| P0-1 / P0-2: letters taken from `log2`, `cos2x`, `sinx`, `lnx`, `5 kg` | Fixed. The parser reads the shorthand and refuses a symbol that exists only inside a function or unit word (`solve/parse.py`). |
| P0-3: complex roots | Fixed. Real roots are kept when one exists; complex roots appear on "complex", "imaginary" or "all roots", or when no real root exists. |
| P0-4: statistics routed to chemistry | Fixed. A bare data list is maths; spreads are labelled σ or s; "mean and standard deviation" is answered together. Lab readings stay chemistry. |
| P0-5: `F = 20 N, m = 5 kg, find a` | Fixed. Physics reads symbol givens (`physics/symbol_givens.py`). A unit-bearing line that no law binds still goes to physics, not algebra. |
| P0-6: scanner drops a term or condition | Fixed. The read-back is the full transcription in written notation (`math/reading.py`), and the equation walker refuses a side cut short by `∛`, `∫` or another symbol. |
| Found while fixing | `∛(x) = 2` answered `x = 2` (fixed: `x = 8`). `a = 3, b = 4, find c` restated a and b (fixed: declines). Dividing `3x = 3` struck out both sides (fixed). |
| Workout format | Shipped (§3), across maths, physics, chemistry, the model prompts, and the phone. |
| The base of a bare `log` | Decided: base 10, as on a school calculator. `log` and `lg` are base 10 and `ln` is natural, in the parser, the phone's graph resampler, and every prompt. Natural logs print as `ln`, and a change of base prints as `log₁₀ x` (`core/sympy_notation.py`). `log(x) = 2` → `x = 100`. |
| Battery of 68 problems (15 topics) | Fixed: `∫1/x` gave `ln(x)` (now `ln\|x\|`); inequalities printed `∧`/`∨` (now `-1 < x < 5`, `x < -1 or x > 1`). Now verified: `what is 5!`, coin and die probabilities, `a right triangle has legs 3 and 4, find the hypotenuse`. Now worked: natural-log and exponential equations, factorable cubics, quadratic inequalities, definite integrals (F(b) − F(a)), finite limits (substitute, factor and cancel, L'Hôpital), distance, slope, midpoint, substitution integrals (`u = sin x`). Later: `6!/4!` was answered by the model, which wrote the left side twice (`6!/4! = 720/24`, then `6!/4! = 30`); factorial arithmetic is now verified and written once (`6!/4! = 720/24`, answer `30`). Tests: `test_math_battery_regressions.py`. |
| Second battery, 70 problems | Fixed wrong answers: mixed numbers (`2 1/2 + 1 3/4` read as `2 × 1/2 + 1 × 3/4`); `f(x) = ...` solved for `f` (now `f(4)`, `f(g(2))` and "evaluate ... when x = 4" substitute); the price before a percent change (48 after 20% off is 60, not 38.4); trig intervals up to 360 read in degrees; tangent and normal lines (were answered with the point) and stationary points with their nature; the second derivative at a point (was the first); `km/hours`; quotient-rule answers simplified; `10.50` trimmed to `10.5` outside the column. Fractions, function values and percent changes write one working line, then the answer. Now verified, each with one working line: geometric sequences (were read as the geometric distribution) and series sums (the "rms" physics cue matched inside "terms"); vectors in round brackets; complex products and quotients; counting in words (`how many ways`, `chosen from`, `k of n`); one roll of dice or one card; the missing leg of a right triangle; polygon angles; the area under a curve (a curve that never crosses the axis used to fail); roots in words; fractions and decimals as percentages; standard form; sums of the first n numbers; completing the square; the cosine rule; "make r the subject". The battery went from 41 direct, 13 verified and 16 unverified to 61 direct and 9 verified. Tests: `test_math_battery_regressions.py`. |
| Third battery, 77 geometry and calculus problems | Fixed wrong answers: a semicircle's area (was the whole circle's); "the radius of a circle with circumference 31.4" (31.4 was read as the radius); a cube's diagonal (no answer); the largest angle from three sides (all three listed); a circle's centre and radius from its equation (solved for x); the gradient of a curve at a point (the point (2, 8)); the area enclosed by two curves with no interval (their meeting points, past a guard that missed "enclosed by"); a Taylor series "up to x^3" ("up to" read as variables); volume of revolution (routed to physics by its "revolution" cue). Now verified: hemispheres, a square from its diagonal, rhombus, equilateral triangles, cuboid diagonals, angle facts, polygon sides from an angle, the sine rule, right-triangle trigonometry, ladders, circle equations, perpendicular gradients and bisectors, triangle area from vertices, implicit dy/dx, increasing intervals, inflection points, average value on [a, b], maximum values, and the two-numbers optimisation. Display: e − 1 (not −1 + e), arctan, series in ascending powers, one-term integrals and limits at infinity with working, dy/dx = f(x) solved by integrating. Battery: 38 direct and 39 to the model became 71 direct and 6 verified. Tests: `test_math_battery_regressions.py`. |
| Open: reach, model lanes, geometry, scanner S2–S6, subject kit | Unchanged; see §4–§9. |

Regression tests: `app/tests/modules/math/test_math_review_regressions.py` and
`app/tests/modules/physics/test_physics_symbol_givens.py`.

## 1. Who answers what

| Lane | When | Who writes the reply |
|---|---|---|
| **Direct verified** | A regex extractor consumes the whole request, SymPy closes it, and the direct guards pass | Server template. No model. |
| **Verified + model** | SymPy closed it, but the turn asks for an explanation with no trace, has several parts, includes a photo, … | The model, told to copy the verified block. Canonical fences are rewritten after the stream. |
| **Detected, unverified** | The math gate fires but no extractor matches, or SymPy declines | The model, told not to claim verification |
| **Not math** | The gate misses | The model, with the general prompt and no math notation contract |

Which model writes the reply (Auto, `modules/chat/model_routing/`, `models/model_catalog.py`):

| Turn | Pro | Free |
|---|---|---|
| Equation, calculus, graph, geometry, stats | GLM 5.2 (`glm-5.2`, thinking off) | **GLM 4.7 Flash** (`glm-4-flash`) |
| Closed arithmetic, factorial | Gemini 2.5 Flash | Gemini 2.5 Flash |
| "Teach me…", an active lesson | Gemini 2.5 Flash | Gemini 2.5 Flash |
| "Prove…" and other smart cues | **DeepSeek R1** (`smart-chat`) | GLM 4.7 Flash |
| Any turn with a photo | Gemini 2.5 Flash (`vision-chat`) | Gemini 2.5 Flash |
| A gate miss (not math) | Gemini 2.5 Flash | Gemini 2.5 Flash |

Hidden helper calls:

| Job | Model | Budget |
|---|---|---|
| Structured-extract fallback (6 kinds; runs only when the gate fires and every regex misses) | Gemini 2.5 Flash, hard-coded `gemini-flash` | 2.5 s |
| Word-problem translator | Gemini 2.5 Flash, then Qwen Plus | 3 s |
| Photo OCR | Mathpix, then Gemini 2.5 Flash | 8 s / 20 s |

Findings:

- **Nobody chose GLM 4.7 Flash for free-plan maths.** `glm-5.2` is Pro-only, so
  `_pick_strongest_from_pool` takes the highest tier in the free pool. That is `glm-4-flash`,
  which has tier "standard" and no price. Choose the free math lane explicitly.
- **Pro proofs go to DeepSeek R1.** `routing.py`'s own comment says R1 "repeatedly emitted only
  hidden reasoning and then fell back". Route proofs to the math lane.
- **Internal jobs reuse the user-selectable `gemini-flash` alias.** Add internal aliases
  (`math-chat`, `math-chat-free`, `math-extract`) so a lane is changed in the catalog, not in
  `llm_extract.py` and `word_problem.py`.
- **No eval decides these lanes.** The cited evidence is "live phone QA". Add an offline eval:
  200 prompts × candidate models, scored on agreement with SymPy and on compliance with the
  workout grammar.

What SymPy alone solves (direct path) and what stays model-only is listed per grade in
[MATH_GRADE_1_12_COVERAGE.md](./MATH_GRADE_1_12_COVERAGE.md). In short, the direct path covers
closed equations (linear, quadratic, power, radical, absolute value, log, rational),
inequalities, systems, derivatives, integrals, limits, written arithmetic, fractions, percent
templates, eight 2D shapes, six solids, coordinates, vectors, matrices, single statistics,
counting, number theory, trig values and equations, complex numbers, units, graphs, check my
work, and word problems after the model translates them. Proofs, "why" questions,
constructions, and multi-step stories outside one system of equations are model-only.

## 2. P0 — wrong answers shipped as verified

Each row is a **direct reply with no model**, as the student sees it.

| Input | Recall replies | Correct | Root cause | Fix |
|---|---|---|---|---|
| `solve log2(x) + log2(x-2) = 3` | Given `2glox + 2glo(x − 2) = 3`, answer `x = 1 + 3/(4glo)` | `x = 4` | `log2(` is not rewritten (only `log_2` is). Implicit multiplication splits it into `l·o·g·2`. | Rewrite `log<digits>(`. Reject any parse with a free symbol the student did not write as a variable. |
| `F = 20 N, m = 5 kg, find a` | "infinitely many solutions, `g = m/(5k)`" | `a = 4 m/s²` (physics) | The physics gate misses `X = value unit` givens. Math reads `kg` as `k·g`. | Same free-symbol guard. Unit tokens block a math claim. Physics accepts a list of given values. |
| `solve e^(2x) = 5` | `x = ln5/2 + πi` or `x = ln5/2` | `x = ½ ln 5 ≈ 0.805` | Equations are solved over ℂ unless the text contains `Abs(` (`solve/parse.py:627`). | Solve over the reals by default; allow complex only on a cue (`i`, "complex", "all roots"). |
| `solve x^3 = 8` / `solve x^4 = 16` | `x = −1 ± √3 i or x = 2` / `x = ±2 or x = ±2i` | `x = 2` / `x = ±2` | Same | Same |
| `standard deviation of 2,4,4,4,5,5,7,9` | Claimed by **chemistry**: sample `s = 2.1` (2 sig figs), chip header `notation: chemistry` | Ambiguous. `variance of` the same list (math) says `4`, the population variance, and √4 ≠ 2.1. | Chemistry's analytical extractor claims any "standard deviation of …" list. Math defaults to population. | A bare data list is math's. One default across subjects, with the answer labelled "sample" or "population". |
| `mean and standard deviation of …` | Chemistry answers `s` only; **the mean is dropped** | Both | The atomicity audit is math's, and chemistry claims the line first | Same as above, plus a cross-subject atomicity check in the dispatcher |

The scanner has the same class of bug; see §6.

P1 fidelity issues found in the same runs:

- **"Given" is not what the student wrote.** `2(x+3)=14` shows `Given: 2x + 6 = 14`, and
  `3(x−2)+4 = 2x+5` shows `3x − 2 = 2x + 5`. The expand and collect steps are skipped silently.
  `log_2(x) = 3` shows `log(x)/log(2) = 3`.
- "…by elimination" returns a substitution trace.
- A definite integral's step label leaks a developer note: "Evaluate (using endpoint limits if
  the integral is improper)".
- `10^x = 50` answers `log(50)/log(10)`, with no `log₁₀ 50 ≈ 1.699`. (Now `log₁₀ 50`; the
  decimal is still missing.)
- The `log_2(x) = 3` lesson repeats `x = 8` on steps 3, 4, and 5, and labels step 2 "Combine
  logarithms" although nothing is combined.
- `show steps: 1234 ÷ 7` does decimal long division to `1234.000` and answers `1234/7 ≈ 176.29`.
  A grade-4 student asking for steps expects `176 R 2`.
- The right-triangle working gives legs as `b` and `h`, then uses the formula `c² = a² + b²`.
- The circle area working shows `≈ 28.27` but not the exact `9π`.

## 3. Workout format

### What ships today

| # | Where | Layout |
|---|---|---|
| A | Equation lesson | `**Given:**`, then `**1. Subtract 3 from both sides**` with the formula on the next line, `**2. Simplify**`, …, `**Answer**`, chip. `2x + 3 = 11` takes 8 rows for two operations; `5x − 7 = 3x + 9` has five numbered steps, two of them "Simplify". |
| B | Derivative | `**Find:**`, then one step whose single formula line holds the rule, the result, and a refactored form. No Answer heading. |
| C | Integral | Numbered method steps, then `**Answer**` |
| D | Definite integral, simplify | Unnumbered bold headings ("Restrictions from the original expression") |
| E | Area between curves | Numbered headings with a blank line between each label and its formula |
| F | Geometry | Given / Find / Formula / Substitution / Answer / Diagram, using two-space hard line breaks |
| G | Physics | The same five sections, with every value its own paragraph: about 12 paragraphs for a two-number problem |
| H | Chemistry | The same five sections as bullets in plain Unicode (`s = √(Σ(x − x̄)² / (n − 1))`), not typeset |
| I | Check my work | `**Line 1** (the problem)`, `**Line 2** ✗`, … |
| J | Model | The prompt asks for Given/Find/Formula/Substitution/Answer, for "a concise answer … an equation does not need a numbered tutorial", and for "one transformation per numbered step". The rules conflict, so the output depends on the model. |

Transport is fragile. The server serializes steps to Markdown, and the phone regex-parses
`**N. label**` plus `$formula$` back into steps (`LESSON_STEP_RE`,
`components/markdown/markdownRenderRules.tsx:93`). A wording change breaks the layout without a
test failing.

### Shipped layout

Shipped on 2026-10-12, keeping the section headings (they make a reply easy to scan). Since
November 2026 **Find** reads **Required**, and a rearrangement is a `Solve for $a$` line of its own
instead of the "rearranged for a" note below; the current layout is in `docs/math.md`. Every
verified reply in maths, physics, and chemistry goes through one formatter,
`apps/api/app/services/workout.py`. The model prompts for all three subjects state the same
layout (`WORKOUT_PROMPT_RULE`).

- **Sections, always in this order, each only when it has lines:** **Given** (the problem as
  the student typed it, or the stated values), **Find** (what is asked), **Formula** (the law
  or rule, its name after the dash), **Substitution** (values put into that formula) or
  **Steps** (an equation changed one move at a time), **Answer** (the chip).
- **Equation lessons number each move.** The heading is the instruction, then the equation
  with that move written on both sides, then the simplified equation, each on its own line.
  `4x + 4 = 0` is `**1. Subtract 4 from both sides**`, `$4x + 4 - 4 = 0 - 4$`, `$4x = -4$`,
  then the same for dividing by 4, ending at `$x = -1$`. A `Simplify` row is that second
  line, not its own number. Physics, chemistry, and geometry keep one state per line with
  the move as a short note (`$2x = 8$ — subtract 3 from both sides`).
- **Given is what was typed.** `3(x−2)+4 = 2x+5` stays as written, and the expansion is its own
  line (`$3x − 2 = 2x + 5$ — expand`). `log₂` is written as `log₂`, not as a change of base.
- **Rules come from the verified trace.** The product, quotient, chain and power rules,
  integration by parts, and the quadratic formula fill Formula. Their names are written as
  names ("— Product rule", "— Newton's second law"); moves are lowercase.
- **One equals sign per line.** A chain continues on the next line with `=`.
- **The phone draws each section as a heading and one row per line**
  (`lib/markdown/workoutSection.ts`, `markdownRenderRules.tsx`), with the note in the secondary
  colour. A stacked fraction no longer pulls a section's lines onto one row.

```text
**Given**
$2x + 3 = 11$

**Find**
$x = ?$

**1. Subtract 3 from both sides**
$2x + 3 - 3 = 11 - 3$
$2x = 8$

**2. Divide both sides by 2**
$2x/2 = 8/2$
$x = 4$

**Answer**
[ x = 4 ]
```

```text
**Given**
$y = x^2 \sin x$

**Find**
$\frac{dy}{dx}$

**Formula**
$(uv)' = u'v + uv'$ — Product rule

**Substitution**
$\frac{d}{dx}(x^2 \sin x) = 2x \sin x + x^2 \cos x$ — product rule with u = x², v = sin x
$= x(x \cos x + 2 \sin x)$

**Answer**
[ x(x cos x + 2 sin x) ]
```

```text
**Given**
$m = 5\,kg$
$F = 20\,N$

**Find**
$a$

**Formula**
$F = ma$ — Newton's second law
$a = \frac{F}{m}$ — rearranged for a

**Substitution**
$a = \frac{20}{5}$

**Answer**
[ 4 m/s² ]
```

`2x + 3 = 11` went from 8 rows to 5 lines plus the chip. Physics went from about 12 paragraphs
to 7 lines.

Still open from the original proposal:

- **W2 — A typed `workout` fence.** The layout is still sent as Markdown. The phone now matches
  the six headings rather than regex-parsing numbered labels, but a typed fence would let copy
  and read-aloud use the same lines.
- **W4 — Golden snapshots** of the rendered reply for 40 canonical problems per subject.
- **W5 — Line budget,** with long derivations folded into sub-steps.
- Tapping a line to show its reason (today the reason appears only when the learner asks
  "why" or "explain").

## 4. Coverage

### Tests

- 78 math test files (18k lines), 3,525 tests, 65 s, **88% line coverage** of
  `app/modules/math` (17,765 statements).
- Lowest files: `tool.py` **43%** (the MCP sympy tool on the tool-loop path, which is on by
  default), `solve/teaching_data.py` 50%, `formulas.py` 54%, `solve/teaching_algebra.py` 66%,
  `tools/extractors/formulas.py` 70%.
- Line coverage is high, but input coverage is not. The golden natural-language corpus
  (`test_math_golden_corpus.py`) has **15 rows**, and none of the §2 inputs is tested.

Add:

- **C1 — Phrasing corpus.** At least 500 prompts by grade and topic, in US, UK, and Ethiopian
  spellings ("factorise", "hcf", "gradient", "x squared minus …"). Each row records its expected
  lane (direct, verified + model, model) and answer. CI reports reach as a percentage.
- **C2 — Independent answer audit** on every direct reply in tests. Substitute the answer into
  the equation parsed from the original text. Every free symbol must appear in the user's text.
  Real domain unless a cue says otherwise.
- **C3 — Cross-subject collision corpus**: statistics vs chemistry, `F = …, m = … kg` vs
  algebra, rates vs physics.
- **C4 — Raise `tool.py` coverage.**

### Reach: 30 everyday phrasings

| Result | Count | Prompts |
|---|---:|---|
| Direct verified | 14 | `find x if 4x - 9 = 23`, `solve for x: 2x + 5 = 3x - 1`, slope through two points, rectangle perimeter, cylinder volume, `sin 30`, expand, 2×2 system, `25% of 360`, miles → km, mean, simplify, quadratic inequality, `7/8 - 1/4` |
| Verified, model writes | 5 | Line through two points, circle area from a diameter, `derivative of x cubed`, `integrate x squared from 0 to 2`, rounding |
| Detected, unverified | 1 | `gradient of y = 3x^2 at x = 2` |
| **Never reaches math** | **10** | `how do I add 3/4 and 5/6`, `what is 2/3 of 45`, `divide 1234 by 7 using long division`, `3/5 as a percentage`, `x squared minus 5x plus 6 equals 0`, missing angle of a triangle, `factorise x^2 + 5x + 6`, rolling a 6 twice, nth term of `3, 7, 11, 15`, `hcf of 24 and 36` |

The ten misses get the general prompt on Gemini 2.5 Flash with no math contract. Fixes:

- **R1** — Widen `needs_symbolic` with curriculum vocabulary: factorise, hcf/gcf, gradient,
  nth term, "as a percentage", "a/b of N", missing angle, and spelled-out operators (squared,
  minus, equals).
- **R2** — When the gate misses but the text has two or more numbers and a math verb, run the
  structured extract. It is already capped at 2.5 s and costs only on a miss.
- **R3** — Extend the structured extract's 6-kind schema to arithmetic, fractions, percent,
  statistics, geometry, probability, and sequences.

### The coverage doc overclaims

[MATH_GRADE_1_12_COVERAGE.md](./MATH_GRADE_1_12_COVERAGE.md) lists box plots, scatter plots,
coin and die trees, stem-and-leaf plots, frequency tables, and point transformations as
"verified pictures". On mobile:

- `box_plot` is the text `min | q1 | median | q3 | max`.
- `scatter`, `probability_tree`, `transformation`, `stem_leaf`, and `frequency_table` fall
  through to `Labeled`, which prints the speech sentence (`components/rich/TeachingCard.tsx:277`).
- The unit circle is a dot inside a ring, with no axes and no angle.

Either draw them (G6) or downgrade the claim.

## 5. Geometry and Skia

| Surface | Renderer |
|---|---|
| Function graphs and the pinch/pan explorer | Skia, with SVG fallback |
| Number line, inequality regions | Skia, with SVG fallback |
| Trajectories, simulations, 3D molecules | Skia |
| **Geometry figures** | **react-native-svg only.** Eight templates, one component per shape: rectangle/square, triangle (base and height), triangle (three sides), right triangle, trapezoid, parallelogram, circle, sector |
| Solids | No figure |
| Teaching pictures | React Native Views; five types are text only |

A shape outside those eight has no drawing at all: polygons, composite figures, circle
theorems, coordinate-geometry figures, transformations, vectors, similar triangles,
constructions, and solids.

Plan:

- **G1 — A geometry scene built on the server.** Primitives: point, segment, ray, polygon,
  circle, arc, angle mark, right-angle mark, equal-length ticks, parallel marks, dimension line,
  and LaTeX label. The server computes coordinates (SymPy geometry or numeric), and every
  printed label must equal a verified value.
- **G2 — One scene renderer with two backends**: Skia on native and SVG as the fallback, the
  same pattern as the graph explorer. Labels use KaTeX_Main on both.
- **G3 — Port the eight templates to server-side scene builders** and delete the eight
  components.
- **G4 — New figures from scene builders**: n-gons, composite areas, circle theorems,
  coordinate figures on the graph axes, transformation pre-image and image, vectors, similar
  triangles.
- **G5 — Solids (MT14)** as a projected 2D scene with dashed hidden edges. No 3D engine needed.
- **G6 — Draw the data pictures**: box plot, scatter (reuse the `GraphCanvas` scatter markers),
  probability tree, stem-and-leaf, frequency table.
- **G7 — Construction step reveal** as a Skia path animation that respects Reduce Motion.

## 6. Scanner

The pipeline: the student crops a photo → `POST /math/scan/read` → Mathpix, accepted when its
confidence is at least 0.72 and the text parses as an equation, system, or inequality →
otherwise Gemini 2.5 Flash returns vision JSON in 10 kinds, with the Mathpix text as a hint →
the reading appears in an editable field → **Solve** sends `Show steps: <reading>` through the
text pipeline, and **Send photo** sends the image with `I read this as: …`.

Mathpix-style LaTeX through the read-back parser (`ocr.extract_from_confirmed_reading`):

| Printed | Read back |
|---|---|
| `\log_2(x)+\log_2(x-2)=3` | `(log(x-2)/log(2)) = 3`: **the first term is gone** |
| `2x + 3 = 7 \quad (x \in \mathbb{Z})` | `2x + 3 = 7`: **the condition is gone** |
| `\frac{1}{2}x+3=7` | `((1)/(2))x+3 = 7` |
| `\|2x-1\|=7` | `Abs(2x-1) = 7` |
| `\sqrt{x+3}=x-3` | `sqrt(x+3) = x-3` |
| `\dfrac{2}{x-1}=\dfrac{3}{x+1}` | Not parsed; goes to vision |
| `\int_0^1 x^2 dx` | Not parsed; goes to vision |
| A system in an `array` | Correct |

Issues:

- **Silent loss (P0).** The student confirms a reading that is not the problem on the page.
- The read-back is ASCII and SymPy notation in a plain text field, with no typeset preview. A
  student cannot confirm `((1)/(2))x`.
- There are two extraction grammars: the text regexes (34 kinds) and the vision JSON schema
  (10 kinds). A photo outside those 10 kinds loses the verified path unless the student taps
  Solve.
- One problem per photo; worksheets have many.
- Handwritten work goes to Solve, not to Check (MT18).
- Biology has no read-back.
- There is no scanner eval set (`docs/fixtures/image_intent_cases.json` has 5 cases).

Plan:

- **S1 (P0)** — Audit consumption between the OCR source and the read-back. On a mismatch, show
  the raw transcription with the uncertain flag.
- **S2** — Show a typeset preview (`MathText`) above the edit field. Read back in student
  notation (½x, |2x − 1|, √(x + 3), x²). Edit with the math keypad.
- **S3** — OCR returns a faithful transcription only, and the text pipeline is the single
  grammar (fix Unicode operators there). Retire the 10-kind vision schema.
- **S4** — On a page with several problems, ask "Which one?" using Mathpix line data.
- **S5** — MT18: a column of lines goes to Check.
- **S6** — An eval set of 200 phone photos, printed and handwritten. Track the transcription
  exact-match rate for Mathpix and for vision.

## 7. Code structure

`modules/math` is 131 files and 33.6k lines.

| Finding | Effect | Proposal |
|---|---|---|
| `MathIntent` is one flat model: 34 kinds, 88 optional fields, and the `operation`, `school_op`, and `teaching_op` sub-switches | Invalid combinations are representable, so every builder re-checks fields | A discriminated union per kind (`Field(discriminator="kind")`) |
| Extraction is spread across `match/` (14 files), `tools/extractors/` (12), `tools/school/` (19), `school.py`, `formulas.py`, and `tools/extractors/formulas.py`, with about 150 pattern tables | One phrase is handled in several places, and the vocabulary gaps in §4 follow | One vocabulary module per topic. Spelled-out math is normalized once, in `prepare()`. |
| Direct-reply eligibility is a 150-line chain of shape-specific `can_direct_*` guards (`tools/direct.py:123`) spread over 13 `direct*.py` files | Every new kind edits the chain | A builder returns `Presentation{workout, answer, figure, direct_ok}`. `direct.py` enforces only the response intent and atomicity. |
| The parse layer splits unknown identifiers into letters (`log2` → `l·o·g·2`, `kg` → `k·g`) and solves over ℂ | P0 rows 1–4 | A free-symbol whitelist, and reals by default |
| Three working representations: math `KeyStep`, physics strings, chemistry `ChemistryResult` | Three layouts | One `Workout` model (W1) |
| The workout is sent as Markdown and regex-parsed on mobile | Fragile | A `workout` fence (W2) |
| Subject dispatch uses a fixed priority: a closed chemistry extraction, then physics, then math | Statistics goes to chemistry; `F = …, m = … kg` goes to math | Each subject returns a claim with confidence and whole-request consumption, and the dispatcher picks one. Covered by the collision corpus (C3). |
| `gemini-flash` is hard-coded in `llm_extract.py` and `word_problem.py` | Changing the lane means changing code | Internal aliases (§1) |

Keep: the fail-closed design (atomicity audit, every trace line verified, the whole trace
dropped when one line fails), subject separation, the SymPy process pool with timeouts,
server-owned fences rewritten after the stream, the native math layout engine, and check my
work.

## 8. Toward maths, physics, chemistry, biology, and economics

Each subject reimplements extract → solve → block → direct → fence. Only
`services/law_binding/` is shared, by physics and chemistry. Extract a subject kit before
adding a subject:

| Kit piece | Source today | Used by |
|---|---|---|
| `Workout`, the `workout` fence, and its renderer | New (W1–W2) | All subjects |
| Answer chip with units, sig figs, and sample/population labels | Math `answer`, chemistry notation | All |
| Law catalog: name, universal form, rearrangements, units | `services/law_binding/` | Physics, chemistry, economics, biology |
| Consumption audit | `modules/math/request_consumption.py` | All |
| Scan read-back | The math, physics, and chemistry scan endpoints | All, biology included |
| Claim-based dispatcher and collision corpus | `services/subjects/dispatch.py` | All |
| Phrasing corpus and golden-snapshot harness | C1, W4 | All |

- **Economics** (deterministic core): supply–demand equilibrium (a 2×2 system, plus a graph
  with labelled curves and the equilibrium point), elasticities (PED, PES, YED, XED), surplus
  areas (geometry-scene triangles), marginal cost and revenue (derivatives), compound interest
  and NPV (already math school templates), GDP deflator, CPI, inflation, the multiplier.
- **Biology** (deterministic core): Punnett squares and genetic ratios, Hardy–Weinberg,
  chi-square, magnification and scale, dilution and serial dilution, exponential and logistic
  growth. Most biology is conceptual and stays with the model, using the same workout grammar
  for any calculation.

## 9. Roadmap

### Phase 0 — correctness (shipped 2026-10-12)

All six are fixed, with regression tests. The property test over the C1 corpus waits for the corpus.

| # | Ticket | Done when |
|---|---|---|
| P0-1 | Free-symbol guard: reject a parse whose free symbols are not variables written in the request (`log2`, `kg`, `sin2x`, …) | Every §2 input declines or answers correctly. A property test runs over the C1 corpus. |
| P0-2 | `log<n>(` and `\log_{n}` sums | `log2(x) + log2(x-2) = 3` → `x = 4`, with the domain step |
| P0-3 | Reals by default | `e^(2x) = 5` → `½ ln 5`; `x^3 = 8` → `2`; complex roots only on a cue |
| P0-4 | Data lists belong to math; label sample or population | Standard deviation and variance agree; "mean and standard deviation" answers both |
| P0-5 | Physics gate for `X = value unit` givens | `F = 20 N, m = 5 kg, find a` → physics |
| P0-6 | Scanner read-back audit (S1) | No term or condition dropped in the §6 table |

### Phase 1 — 2–3 weeks: format, reach, models

- W1 and W3 shipped (one layout and one prompt rule, all three subjects). Left: W2 (typed fence) and W4 (golden snapshots).
- Shipped: "Given" is the student's text with Expand and Collect lines, and no developer notes
  in labels. Left: honor "by elimination"; whole numbers default to a remainder in long division.
- R1–R3, the C1 corpus with reach in CI, and the C2 answer audit.
- Model lanes: an explicit free math lane, proofs off R1, internal aliases, and the eval
  harness.

### Phase 2 — 4–8 weeks: depth

- **Model-drafted workouts audited line by line** by the check-my-work engine
  (`solve/work_check.py`, `work_lines.py`). Lines that pass are marked checked. If a line fails,
  the model retries once, and otherwise the reply is answer-only. This verifies work beyond the
  regex grammars.
- G1–G6: the geometry scene on Skia and SVG, and the data pictures.
- S2–S6 for the scanner.
- The `MathIntent` discriminated union, and builders that return a `Presentation`.

### Phase 3 — new subjects

- Extract the subject kit, then economics v1 and biology v1.
- Solids (G5 / MT14) and verified proofs (MT16).

These tickets overlap the open ones in
[MATH_TUTORING_TICKETS.md](./MATH_TUTORING_TICKETS.md): W5 and MT8 (hints), G5 and MT14, S5 and
MT18.

## How this review was run

```bash
cd apps/api
uv sync --frozen
STEM_SOLVE_TIMEOUT_SECONDS=20 uv run pytest app/tests/modules/math -q \
  --cov=app/modules/math --cov-report=term          # 3525 passed, 88%
```

The prompt sweeps called `build_subject_augmentation(prompt, Settings())` and then
`maybe_direct_subject_reply(...)`, inside an `if __name__ == "__main__":` guard (the SymPy pool
spawns worker processes), with `MATH_LLM_EXTRACT_ENABLED=false` and
`MATH_WORD_PROBLEMS_ENABLED=false` so no model calls ran. Model routing was read from
`routing.resolve_alias_in_pool("auto", prompt, pool)` for the free and Pro pools.
