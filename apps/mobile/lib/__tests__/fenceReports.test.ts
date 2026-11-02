import { classifyFence } from "@/lib/fenceDispatch";
import { fenceReportName, refusalOf } from "@/lib/fenceReports";

describe("refusalOf", () => {
  const kinds = { field: "type", known: ["circle", "sector"] };

  it.each([
    // A JSON fence whose body is not JSON, cut short or prose.
    ['{"type": "circle", "radius": 2', { json: true }, "invalid_json"],
    ["a circle of radius 2", { json: true }, "invalid_json"],
    // A text fence (numbered steps, a SMILES string) that did not read.
    ["nothing numbered here", {}, "invalid_spec"],
    // JSON naming a kind this build does not draw.
    ['{"type": "hexagon", "side": 2}', { json: true, kinds }, "unknown_kind"],
    // A kind it draws, refused by the block's checks.
    ['{"type": "circle", "radius": -2}', { json: true, kinds }, "invalid_spec"],
    ['{"radius": 2}', { json: true, kinds }, "invalid_spec"],
    ['[{"type": "hexagon"}]', { json: true, kinds }, "invalid_spec"],
    ['{"type": 7}', { json: true, kinds }, "invalid_spec"],
  ] as const)("%j %j → %s", (content, shape, reason) => {
    expect(refusalOf(content, shape)).toBe(reason);
  });

  it("is a code, never anything from the body", () => {
    const secret = '{"type": "my private note", "text": "my private note"}';
    expect(refusalOf(secret, { json: true, kinds })).toBe("unknown_kind");
  });
});

describe("fenceReportName", () => {
  it.each([
    ["geometry", '{"type": "circle", "radius": 2}', "geometry"],
    // An alias names the registry's fence, not the tag the reply wrote.
    ["vega-lite", '{"mark": "bar"}', "chart"],
    // A ```json drift that is a graph's schema is that fence.
    ["json", '{"type": "function", "expr": "x", "points": [[0, 0], [1, 1]]}', "graph"],
    // Outside the registry: the block it was drawn as, never the tag.
    ["python", "print(1)", "code"],
    ["my secret tag", "plain words", "code"],
    ["html", "<p>hi</p>", "html"],
  ])("```%s → %s", (lang, content, name) => {
    expect(fenceReportName(classifyFence(lang, content))).toBe(name);
  });
});
