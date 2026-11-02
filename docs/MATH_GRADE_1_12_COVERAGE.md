# Grade 1–12 mathematics coverage

This is a capability audit of the running Recall pipeline, not a list of topics a chat model can
discuss. The code and tests are the source of truth. A topic changes status only when its
extractor, solver, trace, presentation, and regression tests justify the change.

## Status vocabulary

| Status | Product meaning |
|---|---|
| **VERIFIED** | The server deterministically extracts and checks the complete requested result. Presentation must preserve that result. |
| **VERIFIED + PROCEDURE** | The server also owns the ordered school method or derivation. The model may explain the trace but may not recreate it. |
| **TEACH** | Recall can explain the topic using verified facts or examples, but the free-form explanation itself is not certified as a solver trace. |
| **LLM-ONLY** | Conceptual, construction, or proof work is handled as ordinary tutoring prose and must not receive a verification claim. |
| **MISSING** | The current student-facing behavior is not yet reliable or complete enough to claim coverage. |

`VERIFIED` is deliberately narrower than “SymPy knows this.” Extraction must consume the whole
request. A failed or partial extraction falls back without a verification chip.

## Grade-by-grade audit

Curricula vary by country and school. These rows describe the usual grade band and the Ethiopian
Grade 8–10 chapter lists supplied during the audit; they do not claim that every local syllabus
uses the same grade number.

| Grade | Topic | Status | Current behavior | Priority / gap |
|---:|---|---|---|---|
| 1 | Counting and comparing small whole numbers | **TEACH** | The model can teach from ordinary number facts. | Counting counters remain open. A jump that starts negative is verified with the integer arithmetic row. |
| 1 | Single-digit addition and subtraction | **VERIFIED + PROCEDURE** | Exact result. Two digits from 0 to 9 use a number bond when the sum is below 10 and a ten frame when the sum makes ten. Multi-digit addition keeps the column trace. Answer-only turns omit the picture. | Subtraction of two non-negative numbers stays the column trace. |
| 1 | Place value, expanded form, number bonds | **VERIFIED** | Expanded form, the value of a digit that appears once, and base-ten blocks for a whole number up to 999. A repeated digit is declined rather than assigned to one place. | Counting counters, clocks, and money remain separate. |
| 1 | Shapes, length, time, money, simple picture data | **LLM-ONLY** | Ordinary tutoring; no grade-specific manipulative/clock/coin trace. | **P1** for time/money and picture/bar data. |
| 2 | Multi-digit addition and subtraction | **VERIFIED + PROCEDURE** | Carries and regrouping are server-owned, including consecutive borrowing through zero. | Covered for supported numeric grammar. |
| 2 | Skip counting, equal groups, arrays | **VERIFIED** for an array of two factors from 1 to 10; skip counting remains **MISSING** | An equal-group array is the verified picture for that product. | Skip counting has no typed trace. |
| 2 | Measurement, money, clocks, elementary graphs | **TEACH** | Closed arithmetic is verified; interpretation and visuals are prose. | **P1** typed units/time/data teaching. |
| 3 | Multiplication and division facts | **VERIFIED + PROCEDURE** | Exact product/quotient; school working available on request. | Covered. |
| 3 | Multi-digit multiplication and long division | **VERIFIED + PROCEDURE** | Carries, partial products, place shifts, quotient placement, subtract/bring-down cycles, and remainder are typed data. | Covered for integer and supported terminating-decimal cases. |
| 3 | Introductory fractions and fraction of a quantity | **VERIFIED + PROCEDURE** | Exact rational result and typed fraction steps. Addition and subtraction whose common denominator is at most 12 also draw fraction bars. One fraction from 0 to 1 can sit on a number line. | Larger denominators keep the typed steps without bars. |
| 3 | Area/perimeter and elementary data | **VERIFIED** | Closed supported shapes and descriptive statistics are checked. A request for two quantities is declined unless both are represented. | Teaching models incomplete (**P1**). |
| 4 | Whole-number written algorithms | **VERIFIED + PROCEDURE** | Multi-addend addition, subtraction across zero, multiplication, and long division. | Covered. |
| 4 | Factors, multiples, primes | **VERIFIED** | GCD/LCM, primality, factorization, and related number theory. | Explanation remains **TEACH**. |
| 4 | Equivalent/compared/simplified fractions | **VERIFIED + PROCEDURE** | Exact rational arithmetic and common-denominator reasoning. Two-fraction addition and subtraction with a common denominator of at most 12 include fraction bars. | Other visual models remain open. |
| 4 | Angles, lines, area/perimeter | **VERIFIED** for supported numeric shapes; **LLM-ONLY** for definitions/proofs | Canonical geometry result/diagram where the dimensions are complete. | Constructions and theorem teaching **P1**. |
| 5 | Decimal place-value operations | **VERIFIED + PROCEDURE** | Written decimal alignment stays exact. Comparing two decimals names the first place that differs. Rounding to a named place uses half-up. | Rounding to a count of decimal places stays the existing school function. |
| 5 | Fraction operations and mixed numbers | **VERIFIED + PROCEDURE** | Simplify, equivalence, compare, four operations, mixed/improper conversion, quantity. Two-fraction addition and subtraction with a common denominator of at most 12 include fraction bars. | Other fraction pictures remain open. |
| 5 | Percent conversions and applications | **VERIFIED** | Percent-of, change, markup/discount/tax, fraction/decimal expressions in supported grammar. | Unified conversion procedure is **TEACH (P1)**. |
| 5 | Volume and coordinate plane | **VERIFIED** | Supported solids and coordinate computations are checked. | Nets and composed-solid teaching incomplete (**P1**). |
| 6 | Integers and rational-number arithmetic | **VERIFIED** | Exact arithmetic and simplification. A closed sum or difference that starts with a negative integer draws that jump on a number line. | Non-negative subtraction stays the column trace. |
| 6 | Ratios, rates, proportions, percentages | **VERIFIED** | Ratios, splits, direct/inverse proportion, percent applications, and unit conversion. Physical distance/rate/time belongs to physics. | Multi-step ratio stories remain fail-closed unless setup is complete. |
| 6 | Expressions, one-step equations/inequalities | **VERIFIED + PROCEDURE** | Solver-checked transformations and answer/domain guards. | Covered for supported grammar. |
| 6 | Statistics and probability | **VERIFIED** | Descriptive statistics, combinatorics, and supported probability templates. A quartile request draws the box plot from those same quartiles. Closed requests can also draw a frequency table, a stem-and-leaf plot of integers from 0 to 99, a histogram whose integers span at most 15, or a scatter plot of 2 to 12 stated points. | The scatter plot states the points and does not claim a correlation. Sampling design remains **LLM-ONLY**. |
| 7 | Rational numbers, exponents, scientific notation | **VERIFIED** | Exact simplification/evaluation and supported unit/scientific forms. | Grade-specific procedure narration is **TEACH**. |
| 7 | Proportions and percent word problems | **VERIFIED** when every quantity is traceable | Unsupported/underdetermined stories decline verification. | Broader story grammar **P1**. |
| 7 | Equations, inequalities, coordinate geometry | **VERIFIED + PROCEDURE** for equations/inequalities; **VERIFIED** for coordinate formulas | Number-line/region fences use the canonical result. | Covered within closed grammars. |
| 7 | Geometry, transformations, probability | **VERIFIED** for supported calculations and for point translation, reflection in an axis or the origin, rotation by 90, 180, or 270 degrees about the origin, and dilation by a nonzero rational factor of absolute value at most 12, on up to four points. **LLM-ONLY** for proofs and constructions | No invented dimensions. | Constructions remain open. |
| 8 | Linear equations and systems | **VERIFIED + PROCEDURE** | Equation equivalence and 2×2 substitution/elimination traces are checked line by line. | Larger-system answers are verified but teaching is less complete. |
| 8 | Linear inequalities and Cartesian graphs | **VERIFIED + PROCEDURE** / **VERIFIED** | Correct open/closed endpoints, sign reversal, graph/region output. | Covered for supported linear/rational forms. |
| 8 | Squares, roots, cubes, exponents | **VERIFIED** | Exact radicals/powers and equation domains/branches are checked. | First-class radical procedure trace is **TEACH (P1)**. |
| 8 | Similarity, circles, right triangles, trigonometry | **VERIFIED** for closed calculations | Pythagorean, supported circle/triangle/trig results; no fake proof claim. | Formal theorem/construction lessons **LLM-ONLY (P1)**. |
| 8 | Introductory probability | **VERIFIED** | Supported exact probability, expected value, combinations/permutations. A fair coin, two fair coin flips, and a fair die each have a tree whose leaf probabilities sum to 1. | Other probability trees remain open. |
| 9 | Real numbers, radicals, absolute value, quadratics | **VERIFIED + PROCEDURE** for supported equations/inequalities | Domain exclusions, extraneous-root checks, branches, and intervals are retained. | More explicit radical/absolute-value case traces **P1**. |
| 9 | Sets, relations, functions and graphs | **VERIFIED** for set operations and supported function analysis/graphs | Domain/range/inverse/composition where closed and safe. | Relation mapping pedagogy **TEACH**. |
| 9 | Geometry/measurement and trigonometry | **VERIFIED** for supported numeric problems | Canonical formulas, diagrams, units. | Proofs, constructions, composed solids **P1**. |
| 9 | Statistics, probability, vectors | **VERIFIED** for supported calculations | Descriptive/bivariate statistics, probability templates, vector operations. Closed frequency, stem-and-leaf, histogram, scatter, and quartile pictures are verified. | Sampling design and regression interpretation remain **LLM-ONLY**. |
| 10 | Polynomial functions, zeros, factoring and graphs | **VERIFIED**; polynomial and synthetic division are **VERIFIED + PROCEDURE** | Expand/factor/solve/graph and function analysis in supported grammar. A closed division in one variable shows the quotient and remainder, and the long-division remainder matches the polynomial identity. Synthetic division is used when asked and the divisor is monic linear with an integer root. | Fuller radical procedures remain **TEACH**. |
| 10 | Exponential and logarithmic functions/equations | **VERIFIED** | Symbolic simplification/solution/domain checking where SymPy closes the request. | School-method log/exponential trace is **TEACH (P1)**. |
| 10 | Absolute, linear-system and quadratic inequalities | **VERIFIED + PROCEDURE** for supported forms | Correct unions, excluded poles, number lines/regions. | Covered within grammar. |
| 10 | Coordinate geometry and trigonometric functions | **VERIFIED** | Lines, distances, exact trig values, periodic solution branches, graphs. A standard angle within 360 degrees also shows its unit-circle point when that point's sine, cosine, or tangent is the verified value. | Composite angles such as 75 degrees stay on the angle-sum trace. Identity proofs remain **LLM-ONLY**. |
| 10 | Plane geometry and measurement | **VERIFIED** for supported calculations; **LLM-ONLY** for proofs | Triangles, quadrilaterals, circles, regular numeric geometry, solids. | Theorem proofs/constructions/composed solids **P1**. |
| 11 | Algebra II: rational/radical/complex expressions | **VERIFIED** | Exact solve/simplify with domain restrictions and complex arithmetic. | Structured derivations vary; rational/radical procedure **P1**. |
| 11 | Sequences and series | **VERIFIED** | AP/GP terms/sums, infinite GP constraints, supported symbolic series. | Induction/proof is **LLM-ONLY**. |
| 11 | Matrices and vectors | **VERIFIED** | Core matrix and vector operations, eigendata, projections. | Row-operation teaching is **TEACH (P1)**. |
| 11 | Conics, transformations, trig identities/equations | **VERIFIED** for supported closed requests | Canonical expressions/graphs and exact solutions; identities are certified only when symbolic difference is zero. A standard-angle unit-circle point is verified with the trigonometric row. | Conic construction and identity proofs remain **LLM-ONLY**. |
| 11 | Probability/statistics | **VERIFIED** for supported templates | Conditional probability/Bayes, distributions, descriptive/bivariate statistics. | Regression interpretation and sampling design **LLM-ONLY (P1)**. |
| 12 | Limits and derivatives | **VERIFIED + PROCEDURE** | Limits are checked; common derivative rules have validated ordered steps. | Advanced epsilon-delta proofs are **LLM-ONLY**. |
| 12 | Integrals and applications | **VERIFIED + PROCEDURE** for supported antiderivatives; **VERIFIED** for supported applications | Trace is differentiated back; areas/volumes require complete bounds. | Broader techniques/applications **P2**. |
| 12 | Parametric/polar and introductory multivariable calculus | **VERIFIED** for supported closed requests | Parametric/polar graphs, partial derivatives, gradients, multiple integrals where grammar is complete. | Detailed teaching traces **P2**. |
| 12 | Advanced sequences/series and differential equations | **VERIFIED** where the symbolic solver closes | Exact result with explicit bounds/conditions retained. | Convergence-proof teaching and broad ODE classes **LLM-ONLY/P2**. |

## Deterministic procedure inventory

| Procedure | Authoritative data | Verification invariant |
|---|---|---|
| Addition | `ArithmeticWorkSpec` columns with place, addends, carry-in/out, written digit | Rendered result equals the exact sum. |
| Subtraction | Columns with top/bottom digit, borrow source, regrouped value, written digit | Rendered result equals minuend minus subtrahend, including borrowing through zero. |
| Multiplication | Per-row carries, partial product, and decimal/place shift | Sum of shifted partial products equals the exact product. |
| Long division | Quotient digit, partial dividend, multiplication, subtraction, bring-down, remainder | `dividend = divisor × quotient + remainder`; `0 ≤ remainder < |divisor|`. |
| Fractions | `FractionWorkSpec` with exact source/operation/intermediate/result | The reduced rational result is equivalent to the original operation. |
| Teaching pictures | One typed spec per closed request, rendered from the arithmetic fence | The picture's answer is the verified chip. A false or ambiguous picture is declined instead of being answered as a different problem. Polynomial division keeps `quotient × divisor + remainder = dividend`. |
| Equations | Ordered `KeyStep` transformations plus substitution/check | Returned roots satisfy the original equation and restrictions. |
| Inequalities | Ordered trace plus canonical interval/number-line data | Sampled points agree with the original relation; poles remain excluded. |
| Systems | Substitution/elimination trace and canonical tuples | Every tuple satisfies every original equation. |
| Derivatives | Rule-labeled ordered steps | The canonical derivative is symbolically equivalent to differentiating the source. |
| Integrals | Method-labeled ordered steps | Differentiating the reported antiderivative recovers the integrand. |

## Important unsupported or incomplete areas

These are not hidden behind a “complete K–12” percentage:

- **Verified elementary pictures, for a closed request:** place value and base-ten blocks,
  number bonds, ten frames, equal-group arrays, fraction bars, a fraction number line, integer
  jumps that start negative, decimal comparison, and half-up rounding to a named place.
- **Still open elementary work:** counting counters, skip counting, clocks, money, and time.
- **Verified point transformations:** translation, reflection, rotation about the origin, and
  dilation. Formal constructions, proof teaching, and composed solids remain open. Supported
  area-plus-perimeter requests retain both values in one canonical geometry spec and stay off
  the one-answer direct path.
- **Verified algebra pictures:** polynomial long division, synthetic division, and the unit
  circle at a standard angle. Fuller radical and rational-expression procedures, and identity
  proofs, remain open.
- **Verified data pictures:** quartile box plots, frequency tables, stem-and-leaf plots, short
  integer histograms, stated scatter points, and fair coin or die trees. A scatter plot does
  not claim a correlation. Regression interpretation and sampling design remain open.
- **P2 advanced mathematics:** broader integration techniques, convergence proofs, ODE families,
  and detailed parametric/polar/multivariable procedures.

Unsupported multipart prompts are intentionally unverified. For example, if Recall cannot
represent both area and perimeter as one canonical result, it does not certify only one half.

## Maintenance rule

To upgrade a row, add all of the following:

1. a complete-request extractor with meaningful-leftover validation;
2. a deterministic solver and typed result/trace where a procedure is claimed;
3. direct/prompt/fence behavior that cannot change the canonical mathematics;
4. mobile render, reopen, Copy, and read-aloud checks where the representation applies;
5. original, nearby-variant, negative/trap, metamorphic, and invariant tests.

The implementation map and safety boundaries live in [math.md](./math.md). Subject ownership is
locked down in [SUBJECT_SEPARATION_TICKETS.md](./SUBJECT_SEPARATION_TICKETS.md).
