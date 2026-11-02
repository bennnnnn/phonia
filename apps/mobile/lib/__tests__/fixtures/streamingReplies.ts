/**
 * Long model-style replies for the streaming tests: maths with display
 * formulas and an answer card, long bullet and numbered lists (loose, nested,
 * with continuation paragraphs, a lazy line, numbering that does not run on),
 * a table, quotes, code and a callout. The physics and chemistry replies in
 * docs/fixtures and the API's behavior corpus add real server replies.
 */

const FENCE = "```";

export const MATHS_REPLY = String.raw`## Solving $x^2 - 5x + 6 = 0$

We can solve this quadratic three ways. Each one gives the same roots, so pick whichever feels most natural.

### Method 1: Factoring

1. Look for two numbers that multiply to $6$ and add to $-5$.
2. The pair is $-2$ and $-3$, because $(-2)(-3) = 6$ and $-2 + (-3) = -5$.
3. Write the factored form:

$$
(x - 2)(x - 3) = 0
$$

4. Set each factor to zero: $x - 2 = 0$ or $x - 3 = 0$.
5. So $x = 2$ or $x = 3$.

### Method 2: The quadratic formula

For $ax^2 + bx + c = 0$ the roots are

$$
x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}
$$

Here $a = 1$, $b = -5$ and $c = 6$.

- The discriminant is $\Delta = b^2 - 4ac = 25 - 24 = 1$.
- Since $\Delta > 0$, there are **two distinct real roots**.
- Substituting:

$$
x = \frac{5 \pm \sqrt{1}}{2} = \frac{5 \pm 1}{2}
$$

- That gives $x = \frac{6}{2} = 3$ and $x = \frac{4}{2} = 2$.

### Method 3: Completing the square

Move the constant over: $x^2 - 5x = -6$.

Add $\left(\frac{5}{2}\right)^2 = \frac{25}{4}$ to both sides:

$$
x^2 - 5x + \frac{25}{4} = -6 + \frac{25}{4} = \frac{1}{4}
$$

Take square roots: $x - \frac{5}{2} = \pm \frac{1}{2}$, so $x = \frac{5}{2} \pm \frac{1}{2}$, which is $3$ or $2$.

### Comparing the methods

| Method | Best when | Steps |
| --- | --- | --- |
| Factoring | integer roots are easy to spot | 3 |
| Quadratic formula | any quadratic, always works | 4 |
| Completing the square | deriving the vertex form | 5 |

### Checking the answer

- For $x = 2$: $2^2 - 5(2) + 6 = 4 - 10 + 6 = 0$ ✓
- For $x = 3$: $3^2 - 5(3) + 6 = 9 - 15 + 6 = 0$ ✓

Both roots satisfy the equation, so the solution set is $\{2, 3\}$.

### Common mistakes

1. **Dropping a sign.** With $b = -5$, the formula starts with $-b = 5$, not $-5$.
2. **Forgetting the $\pm$.** A quadratic usually has two roots; the $\pm$ produces both.
3. **Dividing only part of the numerator.** The whole of $-b \pm \sqrt{\Delta}$ sits over $2a$.
4. **Squaring a negative carelessly.** $(-5)^2 = 25$, but $-5^2 = -25$.
5. **Stopping before checking.** Substitution takes seconds and catches most slips.

> **Tip:** if the roots come out as messy decimals, check the discriminant again before anything else.

### Key ideas to remember

- The **sum of the roots** is $-\frac{b}{a} = 5$, and $2 + 3 = 5$.
- The **product of the roots** is $\frac{c}{a} = 6$, and $2 \cdot 3 = 6$.
- These relations (Vieta's formulas) are a quick way to check any answer.
- When $\Delta < 0$ there are no real roots; when $\Delta = 0$ there is exactly one repeated root.
- Factoring is fastest when it works, but the formula never fails.

**Answer**

${FENCE}answer
x = 2 \text{ or } x = 3
${FENCE}

If you would like, I can walk through a quadratic whose roots are not integers, such as $2x^2 + 3x - 1 = 0$.
`;

const TIP_TOPICS = [
  "Sleep on a schedule",
  "Walk after meals",
  "Batch your errands",
  "Write tomorrow's first task",
  "Keep water on the desk",
  "Close the inbox while writing",
  "Stretch every hour",
  "Plan meals on Sunday",
  "Read before bed",
  "Call one friend a week",
  "Tidy for ten minutes",
  "Track one habit only",
  "Leave a buffer between meetings",
  "Say no to one thing",
  "Review the week on Friday",
];

/** A long bullet list: bold titles, a dash, a sentence each. */
export const TIPS_REPLY = `Here are fifteen small habits that add up over a month.

${TIP_TOPICS.map(
  (topic, i) =>
    `- **${topic}** – this one takes a few minutes a day and pays back more than it costs, ` +
    `especially once it stops needing willpower (tip ${i + 1}).`,
).join("\n")}

Pick two to start with, and add another each week.
`;

/** A loose numbered list with continuation paragraphs, maths and a code span. */
export const STEPS_REPLY = Array.from({ length: 14 }, (_, i) => {
  const n = i + 1;
  const extra =
    n % 4 === 0
      ? `\n\n   Check it: substitute $x = ${n}$ back in and confirm $${n} \\cdot 2 = ${n * 2}$.`
      : "";
  return `${n}. Step ${n}: multiply the running total by \`factor_${n}\` and record the value.${extra}`;
})
  .join("\n\n")
  .concat("\n\nThat completes the procedure.\n");

/** Nested lists, task items, a lazy line, mixed markers and numbering that does not run on. */
export const NESTED_REPLY = `Packing list for the trip:

- Clothes
  - Two shirts
  - A warm jacket
- Toiletries
  - Toothbrush
- [x] Passport checked
- [ ] Charger packed
- Snacks for the train,
lazy continuation of the snack item.
- Book

* A new list with another marker
* Its second item

1. First
1. Second, numbered 1 again
1. Third, numbered 1 again

10) Ten
11) Eleven
12) Twelve
13) Thirteen

That is everything.
`;

/** A table, a quote with its author, a code fence, a callout and a rule. */
export const MIXED_REPLY = `# Comparing two approaches

The table sums it up:

| Approach | Speed | Memory |
| --- | --- | --- |
| Iterative | fast | low |
| Recursive | slower | high |

> Premature optimization is the root of all evil.
> — Donald Knuth

${FENCE}python
def total(values):
    result = 0
    for value in values:
        result += value
    return result
${FENCE}

> [!note]
> Recursion depth is limited in Python, so prefer the loop for long inputs.

---

## When to choose each

- Use the **iterative** version for large inputs.
- Use the **recursive** version when the problem is naturally recursive.

That is the whole story.
`;

const LONG_SENTENCE = "This sentence adds enough plain words to make the paragraph long enough for a cut. ";

/** Reference-style links whose definitions come last: they resolve only in the piece that holds them. */
export const REFERENCES_REPLY = [
  `Here is a paragraph that cites a source with a [reference-style link][1] and another [second source][docs]. ${LONG_SENTENCE.repeat(5)}`,
  "",
  `Another paragraph in between so that a chunk can end before the definitions. ${LONG_SENTENCE.repeat(5)}`,
  "",
  "[1]: https://example.com/article",
  "[docs]: https://docs.example.com/page",
  "",
].join("\n");

/** A numbered list past 99: its number column is three digits wide, all the way up. */
export const HUNDRED_ITEMS_REPLY = [
  "Here are the words:",
  "",
  ...Array.from({ length: 105 }, (_, i) => `${i + 1}. word number ${i + 1} with a short gloss`),
  "",
  "That is all.",
  "",
].join("\n");

/** From item 10 the sub-bullets sit left of the item's content, so they end the numbered list. */
export const UNDER_INDENTED_REPLY = [
  "Plan:",
  "",
  ...Array.from({ length: 21 }, (_, i) => [
    `${i + 1}. Phase ${i + 1}`,
    `   - sub point one of phase ${i + 1}`,
    `   - sub point two of phase ${i + 1}`,
  ]).flat(),
  "",
  "Done.",
  "",
].join("\n");

export const STREAMING_REPLIES: Record<string, string> = {
  maths: MATHS_REPLY,
  tips: TIPS_REPLY,
  steps: STEPS_REPLY,
  nested: NESTED_REPLY,
  mixed: MIXED_REPLY,
  references: REFERENCES_REPLY,
  hundredItems: HUNDRED_ITEMS_REPLY,
  underIndented: UNDER_INDENTED_REPLY,
};
