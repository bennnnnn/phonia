import {
  dropFences,
  mapClosedFences,
  readFenceMarker,
  readFenceMarkerLoose,
  replaceFirstClosedFenceBody,
  scanFences,
  stripLangFence,
} from "@/lib/mdFenceScan";

describe("replaceFirstClosedFenceBody", () => {
  it("rewrites the first closed fence and keeps surrounding prose", () => {
    const text = "Intro\n```email\nTo: a@b.com\nSubject: Hi\n\nHello\n```\nOutro\n";
    const next = replaceFirstClosedFenceBody(
      text,
      "email",
      "To: b@c.com\nSubject: Bye\n\nShorter",
    );
    expect(next).toBe(
      "Intro\n```email\nTo: b@c.com\nSubject: Bye\n\nShorter\n```\nOutro\n",
    );
  });

  it("returns null when the language fence is missing", () => {
    expect(replaceFirstClosedFenceBody("plain", "email", "Hi")).toBeNull();
  });
});

describe("mapClosedFences", () => {
  it("does not treat a following ```math opener as the previous fence's closer", () => {
    const text = ["```math", "a", "```math", "b"].join("\n");
    const seen: string[] = [];
    const out = mapClosedFences(text, (_info, body, original) => {
      seen.push(body.trim());
      return original;
    });
    expect(seen).toEqual([]);
    expect(out).toContain("```math\na");
    expect(out).toContain("```math\nb");
  });
});

describe("readFenceMarkerLoose", () => {
  it("sees a 4-space-indented ```math that readFenceMarker rejects", () => {
    const line = "    ```math";
    expect(readFenceMarker(line)).toBeNull();
    expect(readFenceMarkerLoose(line)).toEqual({
      char: "`",
      len: 3,
      info: "math",
    });
  });
});

describe("scanFences", () => {
  it("reads each fence with its info, body and range", () => {
    const text = "Intro\n```smiles\nCCO\n```\nOutro";
    const [fence] = scanFences(text);
    expect(fence).toMatchObject({ info: "smiles", body: "CCO", closed: true });
    expect(text.slice(fence!.start, fence!.end)).toBe("```smiles\nCCO\n```");
  });

  it("finds several fences in order", () => {
    const fences = scanFences("```a\n1\n```\n\n```b\n2\n```");
    expect(fences.map((fence) => [fence.info, fence.body])).toEqual([
      ["a", "1"],
      ["b", "2"],
    ]);
  });

  it("keeps a shorter fence inside a longer one as body", () => {
    const fences = scanFences("````md\n```js\nx\n```\n````");
    expect(fences).toHaveLength(1);
    expect(fences[0]!.body).toBe("```js\nx\n```");
  });

  it("reads tilde fences and does not close one with backticks", () => {
    const fences = scanFences("~~~text\n```\nnot a closer\n~~~");
    expect(fences).toHaveLength(1);
    expect(fences[0]!.closed).toBe(true);
    expect(fences[0]!.body).toBe("```\nnot a closer");
  });

  it("runs an unclosed fence to the end, as a streaming reply looks", () => {
    const text = "Hi\n```smiles\nCC";
    const [fence] = scanFences(text);
    expect(fence).toMatchObject({ info: "smiles", body: "CC", closed: false });
    expect(fence!.end).toBe(text.length);
  });

  it("does not take a closer line with an info string for a closer", () => {
    const fences = scanFences("```a\nx\n```b\ny\n```");
    expect(fences).toHaveLength(1);
    expect(fences[0]!.body).toBe("x\n```b\ny");
  });

  it("finds nothing in prose", () => {
    expect(scanFences("no fences here\n\nat all")).toEqual([]);
    expect(scanFences("")).toEqual([]);
  });
});

describe("stripLangFence", () => {
  it("drops every closed fence of the language with its closer's line break", () => {
    expect(stripLangFence("A\n```reminder\n{}\n```\nB\n```reminder\n{}\n```\n", "reminder")).toBe("A\nB\n");
  });

  it("drops a last fence of the language still streaming", () => {
    expect(stripLangFence('A\n```reminder\n{}\n```\nB\n```reminder\n{"ti', "reminder")).toBe("A\nB\n");
  });

  it("keeps other languages, open or closed, and reads the language in any case", () => {
    expect(stripLangFence("A\n```Reminder\n{}\n```\n```reminder_proposal\n{}\n```\n", "reminder")).toBe(
      "A\n```reminder_proposal\n{}\n```\n",
    );
    expect(stripLangFence("A\n```python\nx = 1\n", "reminder")).toBe("A\n```python\nx = 1\n");
  });

  it("leaves a fence shown inside another block alone", () => {
    const text = "~~~text\n```reminder\n{}\n```\n~~~\n";
    expect(stripLangFence(text, "reminder")).toBe(text);
  });
});

describe("dropFences", () => {
  it("reads the rest of the text as before once a fence is dropped", () => {
    const text = "```a\nx\n```\n```b\ny\n```\nend";
    expect(dropFences(text, (span) => span.info === "a")).toBe("```b\ny\n```\nend");
    expect(dropFences(text, () => false)).toBe(text);
  });
});
