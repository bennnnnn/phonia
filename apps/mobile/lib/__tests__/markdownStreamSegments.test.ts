import {
  advanceSegmentScan,
  emptySegmentScan,
  type SegmentScanState,
} from "@/lib/markdown/streamSegments";

/** Every cut the guards offer for `text` read in one go, each accepted. */
function cutsOf(text: string): { cuts: number[]; rewinds: number[]; state: SegmentScanState } {
  const cuts: number[] = [];
  const rewinds: number[] = [];
  const state = advanceSegmentScan(emptySegmentScan(), text, text.length, {
    tryCut: (start) => {
      cuts.push(start);
      return true;
    },
    rewind: (start) => {
      rewinds.push(start);
      return start;
    },
  });
  return { cuts, rewinds, state };
}

/** The lines the cuts land before. */
function cutLines(text: string): string[] {
  return cutsOf(text).cuts.map((at) => text.slice(at, text.indexOf("\n", at)));
}

describe("stream segment cuts", () => {
  it("cuts before a line that follows a blank line", () => {
    expect(cutLines("One.\n\nTwo.\nstill two.\n\nThree.\n")).toEqual(["Two.", "Three."]);
  });

  it("never cuts inside a fence, even across blank lines", () => {
    const text = "Intro.\n\n```python\nx = 1\n\ny = 2\n```\n\nAfter.\n";
    expect(cutLines(text)).toEqual(["```python", "After."]);
  });

  it("stops cutting at a fence marker the passes could read two ways", () => {
    for (const odd of ["Use ``` to open a fence.", "  ```python", "```js```"]) {
      const { cuts, state } = cutsOf(`Intro.\n\n${odd}\n\nLater.\n\nMore.\n`);
      expect(state.poisoned).toBe(true);
      // The cut before it stands; none after it.
      expect(cuts).toEqual(["Intro.\n\n".length]);
    }
    const nested = "```markdown\n```python\nx\n```\n```\n\nLater.\n";
    expect(cutsOf(nested).state.poisoned).toBe(true);
  });

  it.each(["<details><summary>More</summary>", '{"$schema": "https://vega.github.io/schema/"}', "```molecule3d"])(
    "does not cut a reply that holds %s",
    (line) => {
      const { cuts } = cutsOf(`${line}\n\nLater.\n\nMore.\n`);
      expect(cuts).toEqual([]);
    },
  );

  it("holds a worked region together until a fence every pass keeps", () => {
    const text = [
      "**Given**  ",
      "$v = 2$",
      "",
      "**Required**  ",
      "$t$",
      "",
      "```math",
      "t = 1",
      "```",
      "",
      "**Constant speed**",
      "$t = d / v$",
      "",
      "```answer",
      "t = 1",
      "```",
      "",
      "Next part.",
      "",
    ].join("\n");
    expect(cutLines(text)).toEqual(["Next part."]);
  });

  // "Find" is what a reply written before November 2026 calls Required.
  it.each(["Given", "Required", "Find"])(
    "merges a region's parts again when a %s label follows a bold label",
    (label) => {
      const text = `Intro.\n\n**Law name**\n$x = 1$\n\nMore prose.\n\n**${label}**\n$x$\n\nAfter.\n`;
      const { cuts, rewinds } = cutsOf(text);
      expect(cuts.length).toBeGreaterThan(0);
      // The region began at the start of the reply: every part of it is read again.
      expect(rewinds).toEqual([0]);
    },
  );

  it("does not cut while an Answer heading still looks for its card", () => {
    const text = "**Answer**\n\n$x = 2$\n\n```answer\nx = 2\n```\n\nThat is all.\n\nThanks.\n";
    expect(cutLines(text)).toEqual(["That is all.", "Thanks."]);
  });

  it("does not cut inside a check section until a heading", () => {
    const text = "**You can check:**\n\nFor $x = 2$:\n\n$2 + 2 = 4$\n\n## Next\n\nDone.\n";
    expect(cutLines(text)).toEqual(["Done."]);
  });

  it("does not cut while a code tick or a \\( waits for its closer", () => {
    expect(cutLines("A stray ` tick.\n\nLater `code`.\n\nMore.\n")).toEqual([]);
    expect(cutLines("Open \\( x\n\ny \\) closed.\n\nMore.\n")).toEqual(["More."]);
  });

  it("resumes where the last flush stopped", () => {
    const text = "One.\n\nTwo.\n\nThree.\n";
    const cuts: number[] = [];
    const hooks = {
      tryCut: (start: number) => {
        cuts.push(start);
        return true;
      },
      rewind: (start: number) => start,
    };
    let state = advanceSegmentScan(emptySegmentScan(), text, 6, hooks);
    state = advanceSegmentScan(state, text, text.length, hooks);
    expect(cuts).toEqual(cutsOf(text).cuts);
    expect(state.scannedLen).toBe(text.length);
  });
});
