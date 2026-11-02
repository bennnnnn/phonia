import {
  classifyOpenStreamTail,
  parseOpenFenceTail,
  parseOpenMathTail,
} from "@/lib/streamingOpenFence";

describe("parseOpenFenceTail", () => {
  it("splits lang and body from an open ``` fence", () => {
    expect(parseOpenFenceTail("```python\nprint(1)\nprint(2)\n")).toEqual({
      lang: "python",
      body: "print(1)\nprint(2)\n",
    });
  });

  it("handles ~~~ fences and empty bodies", () => {
    expect(parseOpenFenceTail("~~~js\n")).toEqual({ lang: "js", body: "" });
    expect(parseOpenFenceTail("```\n")).toEqual({ lang: "", body: "" });
  });

  it("rejects tails that are not an open fence opener", () => {
    expect(parseOpenFenceTail("just prose")).toBeNull();
    expect(parseOpenFenceTail("``python\nnope")).toBeNull();
  });

  it("BUG FIX regression: strips a closing fence marker that leaked into the open body", () => {
    // Live: ```answer body showed `x = 2 ``` ` (and `` looking like "..")
    // until the fence closed and AnswerBlock remounted without the ticks.
    expect(parseOpenFenceTail("```answer\nx = -2 or x = 2\n```")).toEqual({
      lang: "answer",
      body: "x = -2 or x = 2",
    });
    expect(parseOpenFenceTail("```answer\nx = 2``")).toEqual({
      lang: "answer",
      body: "x = 2",
    });
  });
});

describe("parseOpenMathTail", () => {
  it("strips $$ / \\[ openers", () => {
    expect(parseOpenMathTail("$$\nx^2\n")).toBe("x^2\n");
    expect(parseOpenMathTail("$$x^2")).toBe("x^2");
    expect(parseOpenMathTail("\\[\na+b\n")).toBe("a+b\n");
  });
});

describe("classifyOpenStreamTail", () => {
  it("uses fence classification when the scan says a fence is open", () => {
    expect(
      classifyOpenStreamTail("```ts\nconst x = 1\n", {
        openFence: { char: "`", len: 3 },
        dollarOpen: false,
        bracketDepth: 0,
      }),
    ).toEqual({ kind: "fence", lang: "ts", body: "const x = 1\n" });
  });

  it("uses math classification for open $$", () => {
    expect(
      classifyOpenStreamTail("$$\nE=mc^2\n", {
        openFence: null,
        dollarOpen: true,
        bracketDepth: 0,
      }),
    ).toEqual({ kind: "math", body: "E=mc^2\n" });
  });

  it("falls back to other for prose tails", () => {
    expect(
      classifyOpenStreamTail("still typing", {
        openFence: null,
        dollarOpen: false,
        bracketDepth: 0,
      }),
    ).toEqual({ kind: "other", text: "still typing" });
  });
});
