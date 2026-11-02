import { preprocessMarkdown } from "@/lib/markdown/preprocess";
import {
  findStableMarkdownPrefixLen,
  preprocessMarkdownForStream,
  type StreamingPreprocessCache,
} from "@/lib/markdown/preprocessStream";

/**
 * Simulate a message streaming in by repeatedly growing `full` in chunks of
 * `step` raw characters and feeding it through `preprocessMarkdownForStream`,
 * threading the returned cache back in each time (as `MarkdownContent.tsx`
 * does with its ref). After every tick, cross-checks the incremental
 * result's `rawStableLen` against `findStableMarkdownPrefixLen`, the simple
 * from-scratch reference implementation — the two must always agree.
 */
function simulateStreamingAndCrossCheck(full: string, step: number): void {
  let content = "";
  let cache: StreamingPreprocessCache | null = null;
  for (let i = 0; i < full.length; i += step) {
    content = full.slice(0, Math.min(i + step, full.length));
    const result = preprocessMarkdownForStream(content, cache);
    cache = result.cache;
    expect(cache.rawStableLen).toBe(findStableMarkdownPrefixLen(content));
  }
  expect(content).toBe(full);
}

describe("markdownPreprocessStream", () => {
  it("treats a trailing partial line as unstable", () => {
    expect(findStableMarkdownPrefixLen("Hello wor")).toBe(0);
    expect(findStableMarkdownPrefixLen("Line one\nLine two")).toBe("Line one\n".length);
  });

  it("excludes an unclosed code fence from the stable prefix", () => {
    const input = "Intro\n\n```python\nprint('hi')\n";
    expect(findStableMarkdownPrefixLen(input)).toBe("Intro\n\n".length);
  });

  it("includes a closed code fence in the stable prefix", () => {
    const input = "Intro\n\n```python\nprint('hi')\n```\n\nDone.\n";
    expect(findStableMarkdownPrefixLen(input)).toBe(input.length);
  });

  it("excludes an unclosed ~~~ fence from the stable prefix", () => {
    // Markdown treats ~~~ as equivalent to ``` for code fences. The scanner
    // must toggle fenceOpen for ~~~ openers too, or it would mark the body
    // of a ~~~ fence as stable and the streaming preprocessor would cut
    // mid-fence (rendering a half-open fence).
    const input = "Intro\n\n~~~javascript\nconsole.log('hi')\n";
    expect(findStableMarkdownPrefixLen(input)).toBe("Intro\n\n".length);
  });

  it("includes a closed ~~~ fence in the stable prefix", () => {
    const input = "Intro\n\n~~~javascript\nconsole.log('hi')\n~~~\n\nDone.\n";
    expect(findStableMarkdownPrefixLen(input)).toBe(input.length);
  });

  it("does not let a ~~~ line close a ``` fence", () => {
    // CommonMark: a closer repeats the opener's character, so the ```python fence is
    // still open (markdown-it draws "Done." as code) and nothing after it is stable.
    const input = "Intro\n\n```python\nprint('hi')\n~~~\n\nDone.\n";
    expect(findStableMarkdownPrefixLen(input)).toBe("Intro\n\n".length);
  });

  it("reads a ``` line inside a ~~~ block as its content (audit DUP-03)", () => {
    // Counting fence lines by parity left this how-to unstable to the end.
    const input = "Intro\n\n~~~\n```python\n~~~\n\nDone.\n";
    expect(findStableMarkdownPrefixLen(input)).toBe(input.length);
    expect(preprocessMarkdownForStream(input, null).cache.rawStableLen).toBe(input.length);
  });

  it("reuses cached stable output and leaves the unstable tail raw", () => {
    const stable = "The area is $$\\pi r^2$$ for a circle.\n\n";
    const growing = `${stable}More text in pro`;
    const first = preprocessMarkdownForStream(stable, null);
    const second = preprocessMarkdownForStream(growing, first.cache);

    expect(first.prepared).toContain("```math");
    expect(second.prepared.startsWith(first.prepared)).toBe(true);
    expect(second.prepared.endsWith("More text in pro")).toBe(true);
    expect(second.cache.rawStableLen).toBe(stable.length);
  });

  it("matches full preprocess once the stream completes", () => {
    const content = "The area is $$\\pi r^2$$ for a circle.\n\nTail line.\n";
    const streamed = preprocessMarkdownForStream(content, null).prepared;
    expect(streamed).toBe(preprocessMarkdown(content));
  });

  it("reports a huge unclosed code fence as unstable and stays fast", () => {
    const intro = "Intro before the fence.\n\n";
    const fenceOpen = "```text\n";
    // A single fence opener followed by tens of thousands of characters of
    // filler with no closing ``` — the pathological case that used to make
    // every throttle tick re-walk/re-scan back to the fence's opening line.
    const filler = `${"x".repeat(80)}\n`.repeat(700); // 56,000+ filler chars
    const content = intro + fenceOpen + filler;
    expect(content.length).toBeGreaterThan(50_000);

    const start = Date.now();
    const result = preprocessMarkdownForStream(content, null);
    const elapsed = Date.now() - start;

    // (a) still correctly reported as unstable / not safe to settle: the
    // stable prefix must stop before the fence, and the raw (unprocessed)
    // fence content must still be sitting in the tail.
    expect(result.cache.rawStableLen).toBe(intro.length);
    expect(result.prepared.endsWith(content.slice(intro.length))).toBe(true);
    expect(result.cache.rawStableLen).toBe(findStableMarkdownPrefixLen(content));

    // (b) a single call over 50k+ chars of open structure completes quickly
    // — a sanity check against the quadratic blowup this fixes, not a tight
    // perf assertion (generous bound to avoid CI flakiness).
    expect(elapsed).toBeLessThan(2000);
  });

  it("bounds cumulative cost across many streaming ticks of one still-open fence", () => {
    const intro = "Intro\n\n";
    const fenceOpen = "```text\n";
    const line = `${"y".repeat(60)}\n`;
    const numTicks = 800;

    let content = intro + fenceOpen;
    let cache: StreamingPreprocessCache | null = null;

    const start = Date.now();
    for (let i = 0; i < numTicks; i++) {
      content += line;
      const result = preprocessMarkdownForStream(content, cache);
      cache = result.cache;
      // The stable boundary must never advance into the still-open fence,
      // on any tick, no matter how long the fence has been streaming.
      expect(cache.rawStableLen).toBe(intro.length);
    }
    const elapsed = Date.now() - start;
    // ~800 ticks over a fence that grows past 48,000 chars. With the old
    // whole-prefix re-walk this would be badly superlinear; bounding the
    // total to a generous ceiling guards against that regression without
    // asserting an exact, flake-prone number.
    expect(elapsed).toBeLessThan(3000);

    // Once the fence finally closes, the incremental scan must catch up and
    // agree exactly with the from-scratch reference implementation.
    content += "```\n\nDone.\n";
    const finalResult = preprocessMarkdownForStream(content, cache);
    expect(finalResult.cache.rawStableLen).toBe(content.length);
    expect(finalResult.cache.rawStableLen).toBe(findStableMarkdownPrefixLen(content));
  });

  it("agrees with the reference implementation while streaming a closed fence, math, and a callout", () => {
    const content =
      "Intro\n\n" +
      "```python\nprint('hi')\n```\n\n" +
      "The area is $$\\pi r^2$$ for a circle.\n\n" +
      "> [!note] Heads up\n> keep going\n> and more\n\n" +
      "After the callout.\n";
    simulateStreamingAndCrossCheck(content, 3);
    simulateStreamingAndCrossCheck(content, 17);
  });

  it("agrees with the reference implementation for a callout left open at stream end", () => {
    const content = "Notes\n\n> [!note] Heads up\n> keep going\n";
    simulateStreamingAndCrossCheck(content, 5);
    expect(findStableMarkdownPrefixLen(content)).toBe("Notes\n\n".length);
  });

  it("agrees with the reference implementation for multi-line block math that closes later", () => {
    const content = "Before.\n\n$$\n\\pi r^2\n$$\n\nAfter.\n";
    simulateStreamingAndCrossCheck(content, 4);
  });

  it("BUG FIX regression: excludes an unclosed \\[...\\] block-math delimiter from the stable prefix", () => {
    // preprocessMarkdown's BLOCK_MATH_BRACKET_RE converts \[...\] to a
    // ```math fence just like $$...$$ — but the streaming-stability check
    // only tracked $$, so a still-open \[ used to get folded into the
    // "stable" prefix and preprocessed before its closing \] arrived,
    // leaving a raw dangling "\[" visible mid-stream.
    const input = "Before.\n\n\\[\nx^2 = 4\n";
    expect(findStableMarkdownPrefixLen(input)).toBe("Before.\n\n".length);
  });

  it("agrees with the reference implementation for \\[...\\] block math that closes later", () => {
    const content = "Before.\n\n\\[\n\\pi r^2\n\\]\n\nAfter.\n";
    simulateStreamingAndCrossCheck(content, 4);
  });

  it("matches the reference implementation's position-0 callout-marker quirk", () => {
    // A callout marker as the very first line of the message lacks a
    // preceding "\n", so the original regex never treats it as an unclosed
    // callout even though it looks like one. The incremental scanner must
    // reproduce this exactly, not "fix" it.
    const content = "> [!note] Hi\n> more\n";
    expect(findStableMarkdownPrefixLen(content)).toBe(content.length);
    simulateStreamingAndCrossCheck(content, 6);
  });

  it("a dollar inside a code fence does not hold a later formula", () => {
    const input = "```python\nprice = \"$5\"\n```\n\nThen $x^2$.\n";
    expect(findStableMarkdownPrefixLen(input)).toBe(input.length);
    simulateStreamingAndCrossCheck(input, 5);
  });

  it("BUG FIX regression: excludes an unclosed $...$ inline-math span from the stable prefix", () => {
    // Without tracking single-`$` parity, a prefix cut mid-`$x^2 +` would
    // be treated as stable and preprocessed with a dangling `$`.
    const input = "The answer is $x^2 + \n";
    expect(findStableMarkdownPrefixLen(input)).toBe(0);
  });

  it("BUG FIX regression: includes a closed $...$ inline-math span in the stable prefix", () => {
    const input = "The answer is $x^2$ and more.\n";
    expect(findStableMarkdownPrefixLen(input)).toBe(input.length);
  });

  it("BUG FIX regression: excludes an unclosed \\(...\\) inline-math span from the stable prefix", () => {
    const input = "The answer is \\(x^2 + \n";
    expect(findStableMarkdownPrefixLen(input)).toBe(0);
  });

  it("BUG FIX regression: includes a closed \\(...\\) inline-math span in the stable prefix", () => {
    const input = "The answer is \\(x^2\\) and more.\n";
    expect(findStableMarkdownPrefixLen(input)).toBe(input.length);
  });

  it("agrees with the reference implementation while streaming inline $...$ and \\(...\\) math", () => {
    const content =
      "Intro\n\n" +
      "The value of $x$ is 5.\n\n" +
      "And \\(y = 2x\\) too.\n\n" +
      "After.\n";
    simulateStreamingAndCrossCheck(content, 3);
    simulateStreamingAndCrossCheck(content, 11);
  });

  it("BUG FIX regression: mathFormat is applied during streaming", () => {
    // preprocessMarkdownForStream must forward mathFormat to preprocessMarkdown
    // for the stable prefix — previously it was only applied on the non-streaming path.
    // Use a bare equation (implicit math) so normalizeImplicitMath wraps it via format.
    const content = "x^2 = 4\n";
    const formatFn = (expr: string) => `\\boxed{${expr}}`;
    const result = preprocessMarkdownForStream(content, null, formatFn);
    expect(result.prepared).toContain("\\boxed{x^2 = 4}");
    // Without mathFormat, the default fixImplicitExponents would produce $x^2 = 4$.
    const noFormat = preprocessMarkdownForStream(content, null);
    expect(noFormat.prepared).not.toContain("\\boxed");
  });

  it("does not reuse a stable prefix prepared for the other presentation", () => {
    // A row the server presented can be held in stream layout while it settles;
    // its stable prefix must not come from the draft's cache.
    const content = "Turn at**40 km/h**.\n\nMore tex";
    const draft = preprocessMarkdownForStream(content, null);
    const saved = preprocessMarkdownForStream(content, draft.cache, undefined, { presented: true });
    expect(draft.prepared.startsWith("Turn at **40 km/h**.")).toBe(true);
    expect(saved.prepared.startsWith("Turn at**40 km/h**.")).toBe(true);
    expect(saved.cache.presented).toBe(true);
    expect(preprocessMarkdownForStream(content, saved.cache).prepared).toBe(draft.prepared);
  });

  it("holds back a trailing pipe-table row until the next non-table line", () => {
    const open = "| Month | Rain |\n| --- | --- |\n| Apr | 5.7 |\n";
    expect(findStableMarkdownPrefixLen(open)).toBe(0);
    const closed = "| Month | Rain |\n| --- | --- |\n| Apr | 5.7 |\n\nDone.\n";
    expect(findStableMarkdownPrefixLen(closed)).toBe(closed.length);
  });

  // S7.5: the header used to render as a paragraph of literal pipes, then flip
  // into a table once the delimiter row completed.
  it("never shows a table header's pipes before its delimiter row arrives", () => {
    const full = "Intro\n\n| Name | Age |\n| --- | --- |\n| Ada | 36 |\n\nDone.";
    let cache: StreamingPreprocessCache | null = null;
    for (let i = 1; i <= full.length; i += 1) {
      const raw = full.slice(0, i);
      const result = preprocessMarkdownForStream(raw, cache);
      cache = result.cache;
      const delimiterDone = raw.includes("| --- | --- |\n");
      if (!delimiterDone) expect({ raw, shown: result.prepared }).toEqual({ raw, shown: expect.not.stringContaining("|") });
    }
    expect(preprocessMarkdownForStream("Intro\n\n| a | b |\n", null).prepared).toBe("Intro\n\n");
    expect(preprocessMarkdownForStream("Intro\n\n| a | b |\n|---", null).prepared).toBe("Intro\n\n");
  });

  it("shows the table once its delimiter row is complete, and a pipe line that is no table", () => {
    const table = preprocessMarkdownForStream("| a | b |\n|---|---|\n| 1 | 2", null).prepared;
    expect(table).toContain("| 1 | 2");
    const notTable = preprocessMarkdownForStream("| just a note |\nthen prose\n", null).prepared;
    expect(notTable).toContain("| just a note |");
  });
});
