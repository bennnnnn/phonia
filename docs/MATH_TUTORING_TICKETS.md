# Recall — Math tutoring tickets: verify the learning, not only the answer

The September 2026 math review found the answer path strong: SymPy verifies ~34 kinds and the
app renders the result. What it did not verify was the *learning* — the steps a lesson shows,
a student's own attempt, a word problem's setup, what the camera read. This doc tracks that
work: what shipped in the first pass (MT1–MT6), and what is next.

The rule for every ticket is the same: the model may propose (an extraction, a translation), but
nothing reaches the student as verified until SymPy closes it. A line that fails its check drops
the whole trace, and the turn keeps its normal model path.

## Shipped

| Ticket | What | Where |
|--------|------|-------|
| MT1 | **Verified traces for inequalities and 2×2 systems.** Linear inequalities (swap sides, move terms, divide with the flip for a negative divisor), compound inequalities (all three parts), 2×2 linear systems by substitution or elimination. Every line has the original's solution set or satisfies the solution. Lessons keep the number line; "show steps for …" / "explain how to solve …" reach the solver once the teaching words are removed, but only when math alone is left ("explain why y=mx+b" stays prose). | `solve/traces.py`, `tools/block/algebra.py`, `tools/lesson.py`, `tools/extract.py` |
| MT2 | **Derivative method traces.** Term by term with the rule named: constant, constant multiple, power, product, quotient, chain, exponential, sin/cos/tan/exp/ln. Every line is SymPy's derivative; the last line matches the answer chip. | `solve/derivative_steps.py`, `tools/block/calculus.py` |
| MT3 | **Integral method traces.** Power rule, standard forms, u-substitution (the integrand is f(g(x))·g′(x) up to a constant), integration by parts (LIATE split), with `+ C` once. Every antiderivative is differentiated back. | `solve/integral_steps.py` |
| MT4 | **Check my work.** The student's lines in one unknown (polynomial sides, degree ≤ 2). A line is right when it has line 1's solutions; the first wrong line is named with its slip, every proposed fix is verified, later lines are marked "carried" or wrong. Hint mode ("don't finish it for me") names the slip as a question with no fix or answer — also on the model path. | `tools/work_request.py`, `solve/work_check.py`, `solve/work_lines.py`, `solve/work_slips.py`, `tools/block/work.py` |
| MT5 | **Word-problem compiler.** One structured call translates the problem into unknowns, equations (with the words each comes from) and what is asked. Accepted only when every number is stated in the problem and SymPy finds exactly one solution in the stated domain. Flag `math_word_problems_enabled`. | `tools/word_problem.py`, `solve/word_problem.py`, `tools/block/word.py`, `modules/math/schemas/word_problem.py` |
| MT6 | **Scan review.** `POST /math/scan/read` returns what the camera read (no solve); the scanner shows "I read this as", the student edits and taps Solve (sent as text) or sends the photo with the checked reading. Physics and chemistry use the same review (`POST /physics/scan/read`, `POST /chemistry/scan/read`). Biology still sends the crop with no read-back. | `modules/math/api.py`, `features/scanner/model/readBack.ts`, `features/scanner/components/ScanReadingReview.tsx`, `features/chat/hooks/useChatSend.ts` |

## Next (P1)

- **MT7 — Fraction and percent traces.** `1/2 + 1/3` (common denominator, then add), `15% of 80`,
  percent change, discount then tax: one verified line per operation, on the existing
  `arithmetic` / `school.py` kinds.
- **MT8 — Hint mode for a new problem.** "Just a hint: 2x + 3 = 11" should show the first move
  of the verified trace and stop, not the whole lesson. The hint cue detection exists in
  `work_request.py`; `maybe_direct_math_reply` needs a hint branch for every traced kind.
- **MT9 — Wider check my work.** Rational equations (with the excluded values), radicals
  (squaring is allowed; an extraneous root must be named, not graded as a slip), absolute
  value, and 2×2 systems line by line.
- **MT10 — Calculus application traces.** Optimization (derivative, critical points, the
  second-derivative or endpoint check) and related rates, reusing MT2's rule lines.
- **MT11 — Trig extraction.** Combined and prefixed forms (`2sin(x)cos(x) = 1/2`,
  `sin^2 x + sin x = 0`), with the branch parameter kept.
- **MT18 — Scanned work goes to the checker.** A scan whose reading is a column of lines
  from a problem to an answer is the student's own work. The review could offer **Check**
  beside **Solve** and send `Check my work:` with the lines (today Solve joins them into
  one "Show steps:" problem).
- **MT12 — Weighted statistics and broader probability.** Weighted mean from value/frequency
  tables, conditional probability tables, expected value with a stated distribution.

## Later (P2–P3)

- **MT13 — Implicit and piecewise graphs** (P2). `x^2 + y^2 = 25` beyond the axis-aligned
  ellipse, `y = |x|` pieces, piecewise definitions sampled per piece.
- **MT14 — 3D geometry visuals** (P2). A `solid` diagram fence for the six solids that are
  already verified as numbers.
- **MT15 — Restricted-domain functions** (P2). "f(x) = x^2 on x ≥ 0" is refused today rather
  than peeled; verify range and inverse on the stated domain.
- **MT16 — Verified proofs** (P3). Induction steps checked symbolically (base case, inductive
  step as an identity), not prose.
- **MT17 — Android visual QA.** Golden screenshots for lessons, check-my-work replies and the
  scan review at the largest Android font size (`docs/QA_MATRIX.md` §10, §16).

## Follow-ups found while building MT1–MT6

- Inequalities without a trace (quadratic, rational) still show SymPy's `\wedge` / `\vee` form
  in the answer card; linear and compound ones show the trace's clean last line.
- Derivative and integral answers print `\log`; the lessons' reasons say `ln`.
- The quotient rule's answer card shows SymPy's partly simplified form; the lesson's last line
  matches the card, so both could move to a factored form together.
- "…x^2 sin(x), explain" still parses into a tuple in the old step builder.
- The equation trace's final division cancels on both sides (`\cancel{-2}` over `\cancel{-2}`)
  when the right side equals the divisor.
- A cold SymPy worker takes about 5 s to start in a fresh container, which is the solve
  timeout; local runs of tests that spawn workers need `STEM_SOLVE_TIMEOUT_SECONDS=20`.
