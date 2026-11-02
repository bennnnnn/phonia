import { classifyOpenFencePreview } from "@/lib/fenceDispatch";
import { FENCES } from "@/lib/fenceRegistry";
import { preprocessMarkdownForStream } from "@/lib/markdown/preprocessStream";
import { classifyOpenStreamTail } from "@/lib/streamingOpenFence";

/**
 * Replay a reply one character at a time through the same branch
 * MarkdownContent uses for the live tail (preprocess → classifyOpenStreamTail
 * → classifyOpenFencePreview). Asserts the *sequence* of preview kinds, which
 * settled-output tests cannot see.
 */
function previewSequence(full: string): string[] {
  const kinds: string[] = [];
  let last = "";
  let cache = null as ReturnType<typeof preprocessMarkdownForStream>["cache"] | null;
  for (let i = 1; i <= full.length; i += 1) {
    const raw = full.slice(0, i);
    const result = preprocessMarkdownForStream(raw, cache);
    cache = result.cache;
    const liveRaw = result.prepared.slice(result.cache.preparedStable.length);
    const open = classifyOpenStreamTail(liveRaw, result.cache.scanState);
    let kind = "other";
    if (open.kind === "fence") {
      kind = classifyOpenFencePreview(open.lang, open.body);
    } else if (open.kind === "math") {
      kind = "math";
    }
    if (kind !== last) {
      kinds.push(kind);
      last = kind;
    }
  }
  return kinds;
}

describe("streaming open-fence math dispatch", () => {
  it("BUG FIX regression: open ```latex never lands on CodeBlock (R1)", () => {
    const seq = previewSequence("Here:\n\n```latex\n\\frac{x^2}{2} = 8\n```\n\nDone.");
    expect(seq).not.toContain("code");
    expect(seq).toContain("math");
  });

  it("BUG FIX regression: open ```math does not flip through AnswerBlock (R2)", () => {
    const seq = previewSequence("```math\n\\frac{x^2}{2} = 8\n```\n");
    expect(seq).not.toContain("answer");
    expect(seq).toContain("math");
  });

  it("BUG FIX regression: open ```graph is a quiet diagram, not raw JSON (R3)", () => {
    const seq = previewSequence('```graph\n{"type":"function","points":[[0,0],[1,1]]}\n```\n');
    expect(seq).not.toContain("code");
    expect(seq).toContain("placeholder");
  });

  it("keeps an open server simulation fence as a quiet diagram placeholder", () => {
    const seq = previewSequence(
      '```simulation\n{"type":"free_body","title":"Free-Body Diagram"}\n```\n',
    );
    expect(seq).not.toContain("code");
    expect(seq).toContain("placeholder");
  });

  it("does not flash a gray diagram placeholder for open ```molecule3d", () => {
    const seq = previewSequence("```molecule3d\n     RDKit          3D\n```\n");
    expect(seq).not.toContain("placeholder");
    expect(seq).toContain("hide");
  });

  // S7.4: every Teach-me quiz streamed its JSON in a code block until it closed.
  it.each([
    [
      "quiz",
      '```quiz\n{"label":"Exercise 1","question":"What is d[\\"a\\"]?","options":["1","2"],"answer":0}\n```\n',
    ],
    ["array", '```array\n{"values":[2,7,11,15],"highlight":[0]}\n```\n'],
    ["steps", "```steps\n1. **Read `2` at index `0`**\nWe need `9 - 2 = 7`.\n2. Save it\n```\n"],
    ["places", '```places\n[{"name":"Blue Bottle","url":"https://example.com","note":"0.4 mi"}]\n```\n'],
    ["keyvalue", "```kv\nName: Ada\nRole: Engineer\n```\n"],
    ["comparison", "```pros\nPros:\n- fast\nCons:\n- costly\n```\n"],
  ])("streams an open ```%s fence as a quiet placeholder, never raw source", (_id, reply) => {
    const seq = previewSequence(`Lesson text.\n\n${reply}\nNext.`);
    expect(seq).not.toContain("code");
    expect(seq).toContain("placeholder");
  });

  it("covers every data-bodied fence in the registry, so a new card fence is too", () => {
    const dataFences = FENCES.filter(
      (spec) => spec.body === "data" && spec.id !== "answer" && spec.id !== "molecule3d",
    );
    expect(dataFences.length).toBeGreaterThan(10);
    for (const spec of dataFences) {
      const seq = previewSequence(`\`\`\`${spec.langs[0]}\n{"a": [1, 2, 3], "b": "c"}\n\`\`\`\n`);
      expect({ id: spec.id, seq }).toEqual({ id: spec.id, seq: expect.not.arrayContaining(["code"]) });
    }
  });

  it("streams an open callout or quote as its text, not a code block", () => {
    expect(previewSequence("```tip\nDrink water before you run.\n```\n")).not.toContain("code");
    expect(previewSequence("```quote\nStay hungry.\n— Steve Jobs\n```\n")).toContain("prose");
  });
});
