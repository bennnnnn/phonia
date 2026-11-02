import { classifyFallbackFence } from "@/lib/fallbackFence";

describe("classifyFallbackFence", () => {
  it("classifies callout fences as callouts with the parsed kind", () => {
    expect(classifyFallbackFence("callout-tip", "Try this at home")).toEqual({
      kind: "callout",
      calloutKind: "tip",
      body: "Try this at home",
    });
    expect(classifyFallbackFence("callout-warning", "Heads up")).toEqual({
      kind: "callout",
      calloutKind: "warning",
      body: "Heads up",
    });
  });

  it("treats a bare 'callout' lang as a callout (defaults to note kind)", () => {
    expect(classifyFallbackFence("callout", "Generic note")).toEqual({
      kind: "callout",
      calloutKind: "note",
      body: "Generic note",
    });
  });

  it("classifies unknown langs as code and heavy visuals as summaries", () => {
    expect(classifyFallbackFence("python", "print('hi')")).toEqual({
      kind: "code",
      lang: "python",
      code: "print('hi')",
    });
    expect(classifyFallbackFence("mermaid", "graph TD")).toEqual({
      kind: "visual",
      labelLang: "mermaid",
      snippet: "graph TD",
    });
    expect(classifyFallbackFence("chart", '{"data":[]}')).toEqual({
      kind: "visual",
      labelLang: "chart",
      snippet: "",
    });
  });

  it("summarizes sources and places instead of dumping JSON", () => {
    expect(
      classifyFallbackFence(
        "sources",
        '[{"title":"Docs","url":"https://example.com"}]',
      ),
    ).toEqual({
      kind: "sources",
      items: [{ title: "Docs", url: "https://example.com" }],
    });
    expect(classifyFallbackFence("places", '[{"name":"Cafe"}]')).toEqual({
      kind: "places",
      items: [
        expect.objectContaining({ title: "Cafe" }),
      ],
    });
  });

  it("renders answer fences as a plain result line", () => {
    expect(classifyFallbackFence("answer", "x = 2")).toEqual({
      kind: "answer",
      body: "x = 2",
    });
  });

  it("BUG FIX regression: routes ```graph to SVG instead of dumping points as code", () => {
    const body = JSON.stringify({
      type: "function",
      expr: "x**4 - 4*x**2",
      points: [
        [-2.5, 14.0625],
        [0, 0],
        [2.5, 14.0625],
      ],
    });
    expect(classifyFallbackFence("graph", body)).toEqual({
      kind: "graph",
      body,
    });
  });

  it("BUG FIX regression: routes ```geometry to SVG in the crash fallback", () => {
    const body = JSON.stringify({ type: "square", side: 5, unit: "cm" });
    expect(classifyFallbackFence("geometry", body)).toEqual({
      kind: "geometry",
      body,
    });
  });

  it("trims trailing newlines and whitespace from the body/code", () => {
    expect(classifyFallbackFence("callout-note", "Body\n\n")).toEqual({
      kind: "callout",
      calloutKind: "note",
      body: "Body",
    });
    expect(classifyFallbackFence("js", "code\n")).toEqual({
      kind: "code",
      lang: "js",
      code: "code",
    });
  });

  it("handles missing lang (plain code block)", () => {
    expect(classifyFallbackFence(undefined, "bare code")).toEqual({
      kind: "code",
      lang: "",
      code: "bare code",
    });
  });

  it("uses caption or SMILES for ```molecule JSON and never dumps the SDF", () => {
    const sdf = "Ethanol\n     RDKit          3D\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\nM  END";
    const withCaption = JSON.stringify({ smiles: "CCO", caption: "Ethanol", sdf });
    expect(classifyFallbackFence("molecule", withCaption)).toEqual({
      kind: "visual",
      labelLang: "molecule",
      snippet: "Ethanol",
    });
    const smilesOnly = JSON.stringify({ smiles: "CCO", sdf });
    expect(classifyFallbackFence("molecule", smilesOnly)).toEqual({
      kind: "visual",
      labelLang: "molecule",
      snippet: "CCO",
    });
    const dumped = JSON.stringify(classifyFallbackFence("molecule", withCaption));
    expect(dumped).not.toContain("V2000");
    expect(dumped).not.toContain("RDKit");
  });
});

describe("classifyFallbackFence chemistry answers", () => {
  it("shows a chemistry answer without its notation header", () => {
    expect(
      classifyFallbackFence("answer", "notation: chemistry\nM(H₂O) = 18.02 g/mol\n"),
    ).toEqual({ kind: "answer", body: "M(H₂O) = 18.02 g/mol" });
  });
});
