import {
  advanceStreamBlocks,
  settleStreamBlocks,
  emptyStreamBlocksState,
  MIN_SETTLED_CHUNK_CHARS,
} from "@/lib/markdown/streamBlocks";

const PARA = (label: string) =>
  `${label} ${"lorem ipsum dolor sit amet ".repeat(16).trim()}`;

describe("advanceStreamBlocks", () => {
  it("settles a paragraph at a blank-line boundary once large enough", () => {
    const prepared = `${PARA("First.")}\n\n${PARA("Second.")}\n\ntail…`;
    const state = advanceStreamBlocks(null, prepared, prepared.length);

    expect(state.chunks.length).toBeGreaterThanOrEqual(1);
    expect(state.chunks.join("")).toBe(state.settledText);
    expect(prepared.startsWith(state.settledText)).toBe(true);
    // Chunks end right before the next block starts (cut after the blank run).
    expect(state.chunks[0].endsWith("\n\n")).toBe(true);
  });

  it("keeps everything in the tail until the minimum chunk size is reached", () => {
    const prepared = "Short.\n\nAlso short.\n\n";
    expect(prepared.length).toBeLessThan(MIN_SETTLED_CHUNK_CHARS);
    const state = advanceStreamBlocks(null, prepared, prepared.length);

    expect(state.chunks).toHaveLength(0);
    expect(state.settledText).toBe("");
  });

  it("is append-only while the same reply grows", () => {
    const first = `${PARA("First.")}\n\n${PARA("Second.")}\n\n`;
    const grown = `${first}${PARA("Third.")}\n\nstill streaming`;

    const s1 = advanceStreamBlocks(null, first, first.length);
    const s2 = advanceStreamBlocks(s1, grown, grown.length);

    expect(s2.chunks.slice(0, s1.chunks.length)).toEqual(s1.chunks);
    expect(s2.settledText.startsWith(s1.settledText)).toBe(true);
  });

  it("returns the same state object when nothing new settles", () => {
    const prepared = `${PARA("First.")}\n\n${PARA("Second.")}\n\n`;
    const s1 = advanceStreamBlocks(null, prepared, prepared.length);
    const s2 = advanceStreamBlocks(s1, `${prepared}tail`, prepared.length);

    expect(s2).toBe(s1);
  });

  it("never cuts inside a fenced code block (even across blank lines)", () => {
    const fenceBody = `line one\n\n${PARA("looks like prose")}\n\nline two`;
    const prepared = `\`\`\`python\n${fenceBody}\n\`\`\`\n\n${PARA("After.")}\n\ntail`;
    const state = advanceStreamBlocks(null, prepared, prepared.length);

    for (const chunk of state.chunks) {
      const fenceMarkers = chunk.match(/^```/gm)?.length ?? 0;
      expect(fenceMarkers % 2).toBe(0);
    }
  });

  it("cuts a numbered list only before item 11, where its number column is settled", () => {
    const items = Array.from(
      { length: 12 },
      (_, i) => `${i + 1}. ${"item text ".repeat(8).trim()}`,
    ).join("\n\n");
    const prepared = `${items}\n\n${PARA("After the list.")}\n\ntail`;
    const state = advanceStreamBlocks(null, prepared, prepared.length);

    expect(state.chunks).toHaveLength(1);
    expect(prepared.slice(state.settledText.length).startsWith("11. ")).toBe(true);
    // The chunk ends inside the list: it is drawn as a list that goes on.
    expect(state.continued).toEqual([true]);
    expect(state.listAfter[0]).toEqual(
      expect.objectContaining({ marker: ".", next: 11, irregular: false, wide: false }),
    );
  });

  it("respects the safeLen bound", () => {
    const prepared = `${PARA("First.")}\n\n${PARA("Second.")}\n\ntail`;
    const state = advanceStreamBlocks(null, prepared, 10);

    expect(state.chunks).toHaveLength(0);
  });

  it("resets when the content no longer extends the settled prefix", () => {
    const streamed = `${PARA("First.")}\n\n${PARA("Second.")}\n\n`;
    const s1 = advanceStreamBlocks(null, streamed, streamed.length);
    expect(s1.chunks.length).toBeGreaterThan(0);

    const finalContent = `${PARA("Rewritten.")}\n\n${PARA("Body.")}\n\nend`;
    const s2 = advanceStreamBlocks(s1, finalContent, finalContent.length);

    expect(finalContent.startsWith(s2.settledText)).toBe(true);
    expect(s2.chunks.join("")).toBe(s2.settledText);
  });

  it("starts from a clean state helper", () => {
    expect(emptyStreamBlocksState()).toEqual({
      chunks: [],
      continued: [],
      listAfter: [],
      settledText: "",
      definition: null,
    });
  });

  it(
    "BUG FIX regression: cuts a chunk right after a short closed ```math " +
      "fence instead of waiting for MIN_SETTLED_CHUNK_CHARS",
    () => {
      // Mirrors a real step-by-step math reply: each step's fence body is
      // tiny (well under 320 chars), so under the old size-only threshold
      // this whole segment stayed in the re-parsed-every-flush pending
      // region — remounting the fence's KaTeX WebView on every flush — for
      // as long as it took later steps to push the total past 320 chars.
      const step =
        "1. Subtract 2 from both sides:\n\n```math\nx^2 + 2 - 2 = 6 - 2\n```\n\nSimplify: x^2 = 4\n\n";
      expect(step.length).toBeLessThan(MIN_SETTLED_CHUNK_CHARS);
      const prepared = `${step}2. Take the square root:`;
      const state = advanceStreamBlocks(null, prepared, prepared.length);

      expect(state.chunks.length).toBeGreaterThanOrEqual(1);
      expect(state.chunks[0]).toContain("```math");
      expect(state.settledText.length).toBeLessThan(prepared.length);
    },
  );

  it("still requires a closed fence, not just any short blank-separated text, to cut early", () => {
    // Plain prose with no rich block keeps the existing size-based batching
    // — only a fence/math block should bypass MIN_SETTLED_CHUNK_CHARS.
    const prepared = "Short.\n\nAlso short.\n\ntail";
    expect(prepared.length).toBeLessThan(MIN_SETTLED_CHUNK_CHARS);
    const state = advanceStreamBlocks(null, prepared, prepared.length);

    expect(state.chunks).toHaveLength(0);
  });

  it("cuts eagerly after a short closed $$ display-math block too", () => {
    const prepared = "Here:\n\n$$x^2 = 4$$\n\nDone.\n\ntail";
    expect(prepared.length).toBeLessThan(MIN_SETTLED_CHUNK_CHARS);
    const state = advanceStreamBlocks(null, prepared, prepared.length);

    expect(state.chunks.length).toBeGreaterThanOrEqual(1);
    expect(state.chunks[0]).toContain("$$x^2 = 4$$");
  });

  it("never cuts inside an open fence/math even with the eager rich-block path", () => {
    const prepared = "```math\nx = 1\n\ny = 2\n```\n\ntail";
    const state = advanceStreamBlocks(null, prepared, prepared.length);

    for (const chunk of state.chunks) {
      const fenceMarkers = chunk.match(/^```/gm)?.length ?? 0;
      expect(fenceMarkers % 2).toBe(0);
    }
  });

  it("cuts after a blank before plain text, or before the next item of the open list", () => {
    const parts = [
      `${PARA("One.")}\n\n`,
      // A list's next item may start a chunk; its continuation paragraph may not.
      "- a\n\n  more\n\n",
      "- b\n\n",
      `${PARA("Two.")}\n\n`,
      // A one-line $$…$$ is a rich block: the next safe boundary cuts.
      "Inline $$a$$ here.\n\n",
      // After a quote or a table, plain text past a blank line starts a new block.
      "Short.\n\n",
      "> q\n\n",
      `${PARA("Three.")}\n\n`,
      "| a |\n\n",
      `${PARA("Four.")}\n\nend`,
    ];
    const prepared = parts.join("");
    const state = advanceStreamBlocks(null, prepared, prepared.length);

    expect(state.chunks).toEqual([
      parts.slice(0, 2).join(""),
      parts.slice(2, 5).join(""),
      parts.slice(5, 9).join(""),
    ]);
    expect(state.continued).toEqual([true, false, false]);
  });

  it("settles nothing for a negative safe length", () => {
    const prepared = `${PARA("First.")}\n\n${PARA("Second.")}\n\n`;
    const prev = emptyStreamBlocksState();
    expect(advanceStreamBlocks(prev, prepared, -5)).toBe(prev);
  });
});

describe("advanceStreamBlocks between list items", () => {
  const bullets = (count: number, marker = "-") =>
    Array.from({ length: count }, (_, i) => `${marker} Item ${i + 1}: ${"words ".repeat(14).trim()}`);

  it("cuts a long bullet list between items and says the list goes on", () => {
    const prepared = `Intro.\n\n${bullets(12).join("\n")}\n\nDone.\n\ntail`;
    const state = advanceStreamBlocks(null, prepared, prepared.length);

    expect(state.chunks.length).toBeGreaterThan(1);
    let offset = 0;
    state.chunks.forEach((chunk, index) => {
      offset += chunk.length;
      if (state.continued[index]) {
        expect(prepared.slice(offset)).toMatch(/^- Item \d+:/);
        expect(state.listAfter[index]).toEqual(
          expect.objectContaining({ marker: "-", next: null, irregular: false }),
        );
      }
    });
    expect(state.continued.some(Boolean)).toBe(true);
  });

  it("does not continue a list across a change of bullet marker", () => {
    const prepared = `${bullets(6, "-").join("\n")}\n${bullets(6, "*").join("\n")}\n\ntail`;
    const state = advanceStreamBlocks(null, prepared, prepared.length);
    let offset = 0;
    for (const chunk of state.chunks) {
      offset += chunk.length;
      // The first `*` item opens a new list: never a cut that continues the `-` list.
      expect(prepared.slice(offset).startsWith("* Item 1:")).toBe(false);
    }
  });

  it("never cuts a numbered list whose numbers do not run on, or before item 11", () => {
    const repeated = Array.from({ length: 14 }, () => `1. ${"step words ".repeat(10).trim()}`);
    const short = Array.from({ length: 9 }, (_, i) => `${i + 1}. ${"step words ".repeat(10).trim()}`);
    for (const lines of [repeated, short]) {
      const prepared = `${lines.join("\n")}\n\ntail`;
      expect(advanceStreamBlocks(null, prepared, prepared.length).chunks).toEqual([]);
    }
  });

  it("does not cut a list after a line markdown may read as part of an item", () => {
    const lines = bullets(4);
    const prepared = `${lines[0]}\nlazy line of the first item\n${lines.slice(1).join("\n")}\n${bullets(6).join("\n")}\n\ntail`;
    const state = advanceStreamBlocks(null, prepared, prepared.length);
    expect(state.continued.some(Boolean)).toBe(false);
  });

  it("carries the open list across flushes", () => {
    const lines = Array.from({ length: 14 }, (_, i) => `${i + 1}. ${"step words ".repeat(10).trim()}`);
    const full = `${lines.join("\n")}\n\ntail`;
    const upTo = (n: number) => `${lines.slice(0, n).join("\n")}\n`;
    let state = advanceStreamBlocks(null, upTo(10), upTo(10).length);
    expect(state.chunks).toEqual([]);
    state = advanceStreamBlocks(state, upTo(13), upTo(13).length);
    expect(state.continued).toEqual([true]);
    expect(upTo(13).slice(state.settledText.length).startsWith("11. ")).toBe(true);
    const final = advanceStreamBlocks(state, full, full.length);
    expect(final.chunks.slice(0, 1)).toEqual(state.chunks);
  });

  it("drops a chunk drawn as a list that goes on once the text after it no longer does", () => {
    const lines = Array.from({ length: 13 }, (_, i) => `${i + 1}. ${"step words ".repeat(10).trim()}`);
    const streamed = `${lines.join("\n")}\n`;
    const state = advanceStreamBlocks(null, streamed, streamed.length);
    expect(state.continued).toEqual([true]);
    const chunk = state.chunks[0]!;

    // The same text after it: kept.
    expect(advanceStreamBlocks(state, `${streamed}\nDone.`, 0).chunks).toEqual([chunk]);
    // Its list ends where the chunk does: the chunk is drawn again with its end.
    for (const after of ["Done.\n", "- a bullet\n", "12. skipped a number\n"]) {
      expect(advanceStreamBlocks(state, `${chunk}${after}`, 0).chunks).toEqual([]);
    }
  });

  it("draws a reply holding a link reference definition in one piece, from the line it arrives", () => {
    const body = `${PARA("Cites [a source][1] here.")}\n\n${PARA("Second.")}\n\n${PARA("Third.")}\n\n`;
    const before = advanceStreamBlocks(null, body, body.length);
    expect(before.chunks.length).toBeGreaterThan(0);

    const withDefinition = `${body}[1]: https://example.com/article\n`;
    const after = advanceStreamBlocks(before, withDefinition, withDefinition.length);
    expect(after.chunks).toEqual([]);
    expect(after.definition).toEqual({ at: body.length, line: "[1]: https://example.com/article" });
    // Later flushes find it where it was and cut nothing.
    const later = `${withDefinition}\n${PARA("More text after it.")}\n\n${PARA("And more.")}\n\nend`;
    expect(advanceStreamBlocks(after, later, later.length)).toBe(after);
    // A reply whose definition is still in its last, open line settles in one piece too.
    expect(settleStreamBlocks(before, `${body}[1]: https://example.com/article`).chunks).toEqual([]);
  });

  it("cuts a numbered list that reaches 100 nowhere, even after it was cut while shorter", () => {
    const items = (from: number, to: number) =>
      Array.from({ length: to - from + 1 }, (_, i) => `${from + i}. word number ${from + i} with a short gloss`).join("\n");
    const short = `Words:\n\n${items(1, 60)}\n`;
    const cut = advanceStreamBlocks(null, short, short.length);
    expect(cut.continued.some(Boolean)).toBe(true);

    const long = `Words:\n\n${items(1, 102)}\n`;
    const grown = advanceStreamBlocks(cut, long, long.length);
    expect(grown.continued.some(Boolean)).toBe(false);
    expect(grown.settledText.length).toBeLessThan(long.indexOf("1. word"));
    // And it stays uncut as it goes on.
    const longer = `${long}${items(103, 110)}\n`;
    expect(advanceStreamBlocks(grown, longer, longer.length).continued.some(Boolean)).toBe(false);

    // A reply that only reaches 100 in its last line settles with the list whole.
    const settled = settleStreamBlocks(cut, `Words:\n\n${items(1, 100)}`);
    expect(settled.continued.some(Boolean)).toBe(false);
  });

  it("does not cut a numbered list after a line indented left of its item's content", () => {
    const phases = Array.from({ length: 16 }, (_, i) =>
      [`${i + 1}. Phase ${i + 1} ${"words ".repeat(8).trim()}`, `   - detail of phase ${i + 1}`].join("\n"),
    );
    const prepared = `Plan:\n\n${phases.join("\n")}\n\nDone.\n\ntail`;
    // `10. ` puts item 10's content at column 4: its `   - detail` (column 3) is not inside it.
    expect(advanceStreamBlocks(null, prepared, prepared.length).continued.some(Boolean)).toBe(false);

    // Indented to the item's content, the detail is inside it and the list may be cut.
    const aligned = prepared.replace(/\n   - detail of phase (\d\d)/g, "\n    - detail of phase $1");
    expect(advanceStreamBlocks(null, aligned, aligned.length).continued.some(Boolean)).toBe(true);
  });

  it("drops only the chunks a rewrite changed", () => {
    const streamed = `${PARA("First.")}\n\n${PARA("Second.")}\n\n${PARA("Third.")}\n\n`;
    const s1 = advanceStreamBlocks(null, streamed, streamed.length);
    expect(s1.chunks.length).toBeGreaterThan(1);

    const rewritten = `${s1.chunks[0]}${PARA("Changed.")}\n\n${PARA("More.")}\n\nend`;
    const s2 = advanceStreamBlocks(s1, rewritten, rewritten.length);

    expect(s2.chunks[0]).toBe(s1.chunks[0]);
    expect(s2.chunks.join("")).toBe(s2.settledText);
    expect(rewritten.startsWith(s2.settledText)).toBe(true);
  });
});
