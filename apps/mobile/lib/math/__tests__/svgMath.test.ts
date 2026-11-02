import {
  extractSvgElement,
  latexToSvgMath,
  parseExDimension,
  peekSvgMath,
  clearSvgMathCache,
  setSvgMathRendererForTest,
  svgMathDrawing,
  svgPaintsGlyphs,
  warmSvgMath,
} from "@/lib/math/svgMath";

const CONTAINER =
  '<mjx-container class="MathJax" jax="SVG" display="true">' +
  '<svg style="vertical-align: -1.575ex;" xmlns="http://www.w3.org/2000/svg" width="20.765ex" height="5.291ex" role="img" focusable="false" viewBox="0 -1642.5 9178 2336">' +
  '<g stroke="currentColor" fill="currentColor"><path d="M0 0"></path></g></svg></mjx-container>';

afterEach(() => {
  setSvgMathRendererForTest(null);
});

describe("extractSvgElement", () => {
  it("strips the mjx-container wrapper and the vertical-align style", () => {
    const svg = extractSvgElement(CONTAINER);
    expect(svg).not.toBeNull();
    expect(svg).toContain("<svg");
    expect(svg).not.toContain("mjx-container");
    expect(svg).not.toContain("vertical-align");
    expect(svg).toContain('viewBox="0 -1642.5 9178 2336"');
  });

  it("returns null when there is no svg element", () => {
    expect(extractSvgElement("<div>nope</div>")).toBeNull();
  });
});

describe("parseExDimension", () => {
  it("parses ex dimensions from the svg tag", () => {
    const svg = extractSvgElement(CONTAINER) ?? "";
    expect(parseExDimension(svg, "width")).toBeCloseTo(20.765);
    expect(parseExDimension(svg, "height")).toBeCloseTo(5.291);
  });

  it("rejects missing or non-positive values", () => {
    expect(parseExDimension('<svg height="2ex">', "width")).toBeNull();
    expect(parseExDimension('<svg width="0ex" height="2ex">', "width")).toBeNull();
    expect(parseExDimension('<svg width="abc" height="2ex">', "width")).toBeNull();
  });
});

describe("latexToSvgMath", () => {
  it("renders via the injected renderer and caches by latex+display", async () => {
    const render = jest.fn(() => CONTAINER);
    setSvgMathRendererForTest(render);

    const first = await latexToSvgMath("x^2", true);
    expect(first).not.toBeNull();
    expect(first?.widthEx).toBeCloseTo(20.765);
    expect(first?.svg).toContain("<svg");
    expect(first?.svg).toContain('preserveAspectRatio="xMidYMid meet"');
    expect(first?.svg).not.toContain('width="20.765ex"');

    const second = await latexToSvgMath("x^2", true);
    expect(second).toEqual(first);
    expect(render).toHaveBeenCalledTimes(1);

    await latexToSvgMath("x^2", false);
    expect(render).toHaveBeenCalledTimes(2);
    expect(peekSvgMath("x^2", true)).toEqual(first);
  });

  it("returns null for empty and pathological input without calling the renderer", async () => {
    const render = jest.fn(() => CONTAINER);
    setSvgMathRendererForTest(render);

    expect(await latexToSvgMath("   ", true)).toBeNull();
    expect(await latexToSvgMath("x".repeat(4001), true)).toBeNull();
    expect(render).not.toHaveBeenCalled();
    expect(peekSvgMath("   ", true)).toBeNull();
  });

  it("returns (and caches) null when the renderer throws", async () => {
    const render = jest.fn(() => {
      throw new Error("Undefined control sequence \\nope");
    });
    setSvgMathRendererForTest(render);

    expect(await latexToSvgMath(String.raw`\nope`, true)).toBeNull();
    expect(await latexToSvgMath(String.raw`\nope`, true)).toBeNull();
    expect(render).toHaveBeenCalledTimes(1);
  });

  it("returns null when the container has no svg or bad dimensions", async () => {
    setSvgMathRendererForTest(() => "<div>no svg</div>");
    expect(await latexToSvgMath("x^2", true)).toBeNull();

    setSvgMathRendererForTest(() => '<mjx-container><svg viewBox="0 0 1 1"></svg></mjx-container>');
    expect(await latexToSvgMath("x^3", true)).toBeNull();
  });

  it("rejects an merror bar and a path-less spacer", async () => {
    const errorSvg =
      '<mjx-container><svg xmlns="http://www.w3.org/2000/svg" width="2ex" height="1ex" viewBox="0 0 100 100">' +
      '<g fill="currentColor" data-mml-node="merror"><rect data-background="true" width="100" height="100"></rect></g></svg></mjx-container>';
    setSvgMathRendererForTest(() => errorSvg);
    expect(svgPaintsGlyphs(extractSvgElement(errorSvg) ?? "")).toBe(false);
    expect(await latexToSvgMath(String.raw`\frac{mg}{`, true)).toBeNull();

    const spacer =
      '<mjx-container><svg xmlns="http://www.w3.org/2000/svg" width="0.036ex" height="0.036ex" viewBox="0 0 16 16"></svg></mjx-container>';
    setSvgMathRendererForTest(() => spacer);
    expect(await latexToSvgMath("\\\\", true)).toBeNull();
  });

  it("peekSvgMath is undefined before any attempt", () => {
    setSvgMathRendererForTest(() => CONTAINER);
    expect(peekSvgMath("never-attempted", true)).toBeUndefined();
  });
});

describe("warmSvgMath", () => {
  it("loads the renderer and runs a formula through it, caching nothing", async () => {
    const render = jest.fn(() => CONTAINER);
    setSvgMathRendererForTest(render);
    warmSvgMath();
    await Promise.resolve();
    await Promise.resolve();
    expect(render).toHaveBeenCalledWith("x", true);
    expect(peekSvgMath("x", true)).toBeUndefined();
  });

  it("leaves a renderer that fails for the formula to retry", async () => {
    setSvgMathRendererForTest(() => {
      throw new Error("not loaded");
    });
    expect(() => warmSvgMath()).not.toThrow();
    await Promise.resolve();
    await Promise.resolve();
  });
});

describe("svgMathDrawing", () => {
  it("draws a conversion once per color, and again after the cache is cleared", async () => {
    setSvgMathRendererForTest(() => CONTAINER);
    const result = (await latexToSvgMath("x^2", true))!;
    const draw = jest.fn(() => ({ drawn: true }));
    const first = svgMathDrawing(result, "#111", draw);
    expect(svgMathDrawing(result, "#111", draw)).toBe(first);
    expect(draw).toHaveBeenCalledTimes(1);

    svgMathDrawing(result, "#eee", draw);
    expect(draw).toHaveBeenCalledTimes(2);

    clearSvgMathCache();
    svgMathDrawing(result, "#111", draw);
    expect(draw).toHaveBeenCalledTimes(3);
  });

  it("never hands one formula's drawing to another", async () => {
    setSvgMathRendererForTest((latex) => CONTAINER.replace("M0 0", `M${latex.length} 0`));
    const short = (await latexToSvgMath("a", true))!;
    const long = (await latexToSvgMath("a+b", true))!;
    expect(svgMathDrawing(short, "#111", () => "short")).toBe("short");
    expect(svgMathDrawing(long, "#111", () => "long")).toBe("long");
  });
});
