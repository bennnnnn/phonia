import {
  FENCES,
  fenceIdForLang,
  isNeverCodeBlockLang,
  isStructuredFenceLang,
  fallbackKindForLang,
  isMathFenceLang,
  isMathDiagramLang,
  isChartFenceLang,
  isControlFenceLang,
  isVisualDiagramFenceLang,
  isDataBodyFenceId,
  shouldLiftFenceOutOfList,
  documentFormForLang,
  drawsBareJson,
  fenceSpecForLang,
} from "@/lib/fenceRegistry";

/**
 * Characterization test: the registry must reproduce the pre-existing language
 * sets exactly, plus deliberate additions. These literals started as the lists
 * in richBlocks.ts (STRUCTURED_LANGS) and copyBlock.ts (isExplicitCodeLang's
 * exclusions) before the registry existed. `latex`/`tex` were added as aliases
 * of `math` so an open streaming ```latex fence typesets instead of CodeBlock.
 * If a future change to FENCES alters what renders, it fails here rather than
 * silently in the app.
 */

const LEGACY_STRUCTURED = [
  "email",
  "quote",
  "blockquote",
  "compare",
  "comparison",
  "pros",
  "kv",
  "keyvalue",
  "fields",
  "steps",
  "step",
  "math",
  "latex",
  "tex",
  "answer",
  "result",
  "final",
  "arithmetic",
  "clock",
  "time",
  "mermaid",
  "chart",
  "vega",
  "vega-lite",
  "plot",
  "geometry",
  "graph",
  "simulation",
  "calculator",
  "chem_scene",
  "smiles",
  "chemistry",
  "molecule",
  "molecule3d",
  "mol3d",
  "3dmol",
  "places",
  "quiz",
  "clarify",
  "array",
  // callout langs
  "tip",
  "note",
  "warning",
  "info",
  "important",
  "callout",
  // social langs
  "twitter",
  "tweet",
  "x",
  "linkedin",
  "facebook",
  "fb",
  "instagram",
  "insta",
  "ig",
  "tiktok",
  "threads",
  "caption",
  "social",
  // message langs
  "sms",
  "message",
  "reply",
];

const LEGACY_NEVER_CODE_BLOCK = [
  "copy",
  "message",
  "email",
  "sms",
  "reply",
  "twitter",
  "tweet",
  "x",
  "linkedin",
  "facebook",
  "fb",
  "instagram",
  "insta",
  "ig",
  "tiktok",
  "threads",
  "caption",
  "social",
  "clock",
  "time",
  "sources",
  "places",
  "quiz",
  "clarify",
  "array",
  "graph",
  "simulation",
  "geometry",
  "calculator",
  "chem_scene",
  "smiles",
  "chemistry",
  "molecule",
  "molecule3d",
  "mol3d",
  "3dmol",
  "math",
  "latex",
  "tex",
  "answer",
  "result",
  "final",
  "arithmetic",
];

describe("fence registry reproduces the legacy language sets", () => {
  it.each(LEGACY_STRUCTURED)("%s is structured", (lang) => {
    expect(isStructuredFenceLang(lang)).toBe(true);
  });

  it("marks nothing else as structured", () => {
    const registered = FENCES.filter((f) => f.structured).flatMap((f) => f.langs);
    expect([...registered].sort()).toEqual([...LEGACY_STRUCTURED].sort());
  });

  it.each(LEGACY_NEVER_CODE_BLOCK)("%s is never a code block", (lang) => {
    expect(isNeverCodeBlockLang(lang)).toBe(true);
  });

  it("marks nothing else as never-code-block", () => {
    const registered = FENCES.filter((f) => f.neverCodeBlock).flatMap((f) => f.langs);
    expect([...registered].sort()).toEqual([...LEGACY_NEVER_CODE_BLOCK].sort());
  });
});

describe("fence registry lookups", () => {
  it("resolves callout-* variants to the callout fence", () => {
    expect(fenceIdForLang("callout-tip")).toBe("callout");
    expect(fenceIdForLang("callout-warning")).toBe("callout");
    expect(isStructuredFenceLang("callout-note")).toBe(true);
  });

  it("is case and whitespace insensitive", () => {
    expect(fenceIdForLang("  GEOMETRY ")).toBe("geometry");
    expect(isStructuredFenceLang(" Mermaid")).toBe(true);
  });

  it("does not route collapsed-answer langs to a fence", () => {
    for (const lang of ["details", "collapse", "summary"]) {
      expect(fenceIdForLang(lang)).toBeNull();
      expect(isStructuredFenceLang(lang)).toBe(false);
    }
  });

  it("returns null for unknown and code languages", () => {
    for (const lang of ["python", "javascript", "json", "", "rust"]) {
      expect(fenceIdForLang(lang)).toBeNull();
      expect(isStructuredFenceLang(lang)).toBe(false);
      expect(isNeverCodeBlockLang(lang)).toBe(false);
    }
  });

  it("keeps copy and sources out of the rich renderer but out of code blocks too", () => {
    for (const lang of ["copy", "sources"]) {
      expect(isStructuredFenceLang(lang)).toBe(false);
      expect(isNeverCodeBlockLang(lang)).toBe(true);
    }
  });

  it("declares crash-fallback handling for callout, diagrams, answers, and transport", () => {
    expect(fallbackKindForLang("callout-tip")).toBe("callout");
    expect(fallbackKindForLang("geometry")).toBe("geometry");
    expect(fallbackKindForLang("graph")).toBe("graph");
    expect(fallbackKindForLang("answer")).toBe("answer");
    expect(fallbackKindForLang("sources")).toBe("sources");
    expect(fallbackKindForLang("places")).toBe("places");
    expect(fallbackKindForLang("mermaid")).toBe("visual");
    expect(fallbackKindForLang("chart")).toBe("visual");
    expect(fallbackKindForLang("python")).toBeNull();
  });

  it("marks every fence as model, server, or legacy", () => {
    for (const spec of FENCES) {
      expect(["model", "server", "legacy"]).toContain(spec.owner);
    }
    expect(FENCES.find((f) => f.id === "email")?.owner).toBe("model");
    expect(FENCES.find((f) => f.id === "answer")?.owner).toBe("server");
    expect(FENCES.find((f) => f.id === "steps")?.owner).toBe("model");
    expect(FENCES.find((f) => f.id === "molecule")?.owner).toBe("server");
    expect(fenceIdForLang("molecule")).toBe("molecule");
    expect(fenceIdForLang("molecule3d")).toBe("molecule3d");
  });

  it("has no duplicate language tag across fences", () => {
    const all = FENCES.flatMap((f) => f.langs);
    expect(new Set(all).size).toBe(all.length);
  });

  it("does not add fence types without an explicit contract change", () => {
    expect(FENCES.map((spec) => spec.id).sort()).toEqual([
      "answer",
      "arithmetic",
      "array",
      // Server-owned: docs/money.md; the server writes it after the reply.
      "calculator",
      "callout",
      "chart",
      "chem_scene",
      "chemistry",
      "clarify",
      "clock",
      "comparison",
      "copy",
      "email",
      "geometry",
      "graph",
      "keyvalue",
      "math",
      "mermaid",
      "message",
      "molecule",
      "molecule3d",
      "places",
      "quiz",
      "quote",
      // P14. Server-owned like geometry/graph: the prompt forbids it and
      // validate_math_fences replaces or strikes out anything the model
      // invents, so the model-owned list below is unchanged.
      "simulation",
      "social",
      "sources",
      "steps",
    ]);
    expect(
      FENCES.filter((spec) => spec.owner === "model").map((spec) => spec.id).sort(),
    ).toEqual([
      "array",
      "chart",
      "chemistry",
      "clarify",
      "copy",
      "email",
      "math",
      "mermaid",
      "message",
      "places",
      "quiz",
      "social",
      "steps",
    ]);
  });

  it("treats latex/tex as math fence aliases (open-stream typeset, not CodeBlock)", () => {
    expect(fenceIdForLang("latex")).toBe("math");
    expect(fenceIdForLang("tex")).toBe("math");
    expect(isMathFenceLang("latex")).toBe(true);
    expect(isMathDiagramLang("geometry")).toBe(true);
    expect(isMathDiagramLang("python")).toBe(false);
  });
});

describe("fence registry round-trip (render, copy, fallback)", () => {
  it("every registered id has an explicit render slot", () => {
    const renderSlot: Record<(typeof FENCES)[number]["id"], "component" | "hidden"> = {
      email: "component",
      quote: "component",
      comparison: "component",
      keyvalue: "component",
      steps: "component",
      math: "component",
      answer: "component",
      arithmetic: "component",
      clock: "component",
      mermaid: "component",
      chart: "component",
      geometry: "component",
      graph: "component",
      simulation: "component",
      calculator: "component",
      chem_scene: "component",
      chemistry: "component",
      molecule: "component",
      molecule3d: "component",
      places: "component",
      quiz: "component",
      clarify: "component",
      array: "component",
      callout: "component",
      social: "component",
      message: "component",
      copy: "hidden",
      sources: "hidden",
    };
    for (const spec of FENCES) {
      expect(renderSlot[spec.id]).toBe(spec.structured ? "component" : "hidden");
    }
  });

  it("copy/speech routing derives from the registry, not parallel lang lists", () => {
    expect(isChartFenceLang("vega-lite")).toBe(true);
    expect(isVisualDiagramFenceLang("smiles")).toBe(true);
    expect(isVisualDiagramFenceLang("chart")).toBe(false);
    expect(isControlFenceLang("sources")).toBe(true);
    expect(isControlFenceLang("reminder")).toBe(true);
    expect(isControlFenceLang("python")).toBe(false);
    expect(isDataBodyFenceId("mermaid")).toBe(true);
    expect(isDataBodyFenceId("quiz")).toBe(true);
    expect(isDataBodyFenceId("clarify")).toBe(true);
    expect(isDataBodyFenceId("callout")).toBe(false);
    expect(shouldLiftFenceOutOfList("latex")).toBe(true);
    expect(shouldLiftFenceOutOfList("python")).toBe(false);
  });

  it("every fence's fallback kind matches the registry declaration", () => {
    for (const spec of FENCES) {
      expect(fallbackKindForLang(spec.langs[0]!)).toBe(spec.fallback ?? null);
    }
  });
});

describe("per-fence predicates accept exactly these fences", () => {
  // Every registered tag, a callout variant, the unregistered control tags and
  // a few code tags: each predicate below is pinned over all of them.
  const probes = [
    ...FENCES.flatMap((spec) => spec.langs),
    "callout-tip",
    "reminder",
    "reminder_proposal",
    "settings_proposal",
    "calendar_proposal",
    "photo",
    "python",
    "json",
    "",
  ];
  const accepted = (predicate: (lang: string) => boolean) =>
    [...new Set(probes.filter(predicate).map((lang) => fenceIdForLang(lang) ?? lang))].sort();

  it("display maths and maths diagrams", () => {
    expect(accepted(isMathDiagramLang)).toEqual(["arithmetic", "geometry", "graph", "math"]);
  });

  it("fences lifted out of list items", () => {
    expect(accepted(shouldLiftFenceOutOfList)).toEqual([
      "answer",
      "arithmetic",
      "geometry",
      "graph",
      "math",
    ]);
  });

  it("charts and diagrams read aloud by name", () => {
    expect(accepted(isChartFenceLang)).toEqual(["chart"]);
    expect(accepted(isVisualDiagramFenceLang)).toEqual([
      "arithmetic",
      "chem_scene",
      "chemistry",
      "geometry",
      "graph",
      "mermaid",
      "molecule",
      "molecule3d",
      "simulation",
    ]);
  });

  it("control fences, never copied or spoken", () => {
    expect(accepted(isControlFenceLang)).toEqual([
      "calculator",
      "calendar_proposal",
      "photo",
      "places",
      "reminder",
      "reminder_proposal",
      "settings_proposal",
      "sources",
    ]);
  });

  it("maths fences", () => {
    expect(accepted(isMathFenceLang)).toEqual(["math"]);
  });

  // The lists plain.ts, document.ts and fenceDispatch.ts kept beside the registry (ST-09), now rows.
  it("bodies copy and read-aloud draw with their own reader", () => {
    const readers = FENCES.flatMap((spec) => {
      const reader = spec.plainReader;
      return reader ? [`${spec.id}:${reader}`] : [];
    });
    expect(readers.sort()).toEqual(["arithmetic:worked", "array:array", "clarify:clarify", "quiz:quiz"]);
  });

  it("what a shared document shows in each card's place", () => {
    const forms = Object.fromEntries(
      FENCES.flatMap((spec) => {
        const form = documentFormForLang(spec.langs[0]!);
        return form ? [[spec.id, form]] : [];
      }),
    );
    expect(forms).toEqual({
      arithmetic: "copyText",
      quiz: "copyText",
      clarify: "copyText",
      array: "copyText",
      calculator: "calculator",
      places: "places",
      graph: "graph",
      chemistry: "molecule",
      molecule: "molecule",
      molecule3d: "molecule",
      chart: "chart",
      geometry: "diagram",
      mermaid: "diagram",
      simulation: "diagram",
      chem_scene: "diagram",
    });
  });

  it("drafts, and the cards drawn as a molecule", () => {
    expect(accepted((lang) => fenceSpecForLang(lang)?.draft ?? false)).toEqual(["email", "message", "social"]);
    expect(accepted((lang) => documentFormForLang(lang) === "molecule")).toEqual([
      "chemistry",
      "molecule",
      "molecule3d",
    ]);
  });

  it("cards a bare ```json fence of their JSON draws as", () => {
    expect(FENCES.filter((spec) => drawsBareJson(spec.id)).map((spec) => spec.id).sort()).toEqual([
      "geometry",
      "graph",
    ]);
  });
});
