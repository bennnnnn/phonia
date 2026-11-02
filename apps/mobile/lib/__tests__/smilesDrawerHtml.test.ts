import {
  buildSmilesDrawerPageHtml,
  readSmilesDrawerError,
  SMILES_DRAWER_ERROR_KIND,
  SMILES_DRAWER_PAGE,
  smilesDrawerConfig,
} from "@/lib/chemistry/smilesDrawerHtml";

import { previewPageSandbox } from "./fixtures/previewPageSandbox";

const THEME = { bg: "#ffffff", isDark: false };
const LIBRARY = "(function () { return function () {}; })()";

/** SmilesDrawer's SvgDrawer and parse, recording what the page asks of them. */
function fakeSmilesDrawer(options: { parses?: boolean; draws?: boolean } = {}) {
  const drawn: unknown[][] = [];
  const parsed: string[] = [];
  class SvgDrawer {
    preprocessor = { processGraph: () => undefined, graph: { vertices: [{ value: {} }] } };
    draw(...args: unknown[]) {
      if (options.draws === false) throw new Error("draw failed");
      drawn.push(args);
    }
  }
  const parse = (smiles: string, ok: (tree: unknown) => void, fail: () => void) => {
    parsed.push(smiles);
    if (options.parses === false) fail();
    else ok({ tree: smiles });
  };
  return { SmilesDrawer: { SvgDrawer, parse }, drawn, parsed };
}

describe("buildSmilesDrawerPageHtml", () => {
  it("is one page for every structure: the library once, no SMILES, no network", () => {
    const html = SMILES_DRAWER_PAGE.build({ smilesDrawer: LIBRARY });
    expect(SMILES_DRAWER_PAGE.libraries).toEqual(["smilesDrawer"]);
    expect(html).toBe(buildSmilesDrawerPageHtml(LIBRARY));
    expect(html.split(LIBRARY)).toHaveLength(2);
    expect(html).toContain("var SmilesDrawer = __sdReq(1);");
    expect(html).toContain("Content-Security-Policy");
    expect(html).toContain("connect-src 'none'");
    expect(html).not.toContain(THEME.bg);
  });

  it("reports failure by code, leaving the words to the app", () => {
    const html = buildSmilesDrawerPageHtml(LIBRARY);
    expect(html).toContain(`kind: '${SMILES_DRAWER_ERROR_KIND}'`);
    expect(html).toContain("reportError('render')");
    expect(html).toContain("reportError('unavailable')");
    expect(html).not.toContain("Could not render");
  });
});

describe("the structure page", () => {
  it("draws the SMILES it is handed, every atom explicit, in the block's theme", () => {
    const drawer = fakeSmilesDrawer();
    const page = previewPageSandbox({ SmilesDrawer: drawer.SmilesDrawer });
    page.loadPage(buildSmilesDrawerPageHtml(LIBRARY));
    page.hand(smilesDrawerConfig("  CC(=O)Oc1ccccc1C(=O)O \n", { bg: "#101010", isDark: true }));
    expect(drawer.parsed).toEqual(["CC(=O)Oc1ccccc1C(=O)O"]);
    expect(drawer.drawn).toEqual([[{ tree: "CC(=O)Oc1ccccc1C(=O)O" }, page.elements.molecule, "dark"]]);
    expect(page.css).toEqual({ "--bg": "#101010" });
    expect(page.posted).toEqual([]);
  });

  it.each([
    ["a SMILES it cannot parse", { parses: false }],
    ["a structure it cannot draw", { draws: false }],
  ])("reports %s as a render error", (_name, options) => {
    const page = previewPageSandbox({ SmilesDrawer: fakeSmilesDrawer(options).SmilesDrawer });
    page.loadPage(buildSmilesDrawerPageHtml(LIBRARY));
    page.hand(smilesDrawerConfig("C1CC", THEME));
    expect(page.posted).toEqual([{ kind: SMILES_DRAWER_ERROR_KIND, code: "render" }]);
  });

  it("reports a library that did not load as unavailable", () => {
    const page = previewPageSandbox({ SmilesDrawer: undefined });
    page.loadPage(buildSmilesDrawerPageHtml(LIBRARY));
    page.hand(smilesDrawerConfig("CCO", THEME));
    expect(page.posted).toEqual([{ kind: SMILES_DRAWER_ERROR_KIND, code: "unavailable" }]);
  });

  it.each([
    ["a backtick", "C`C"],
    ["a template placeholder", "C${alert(1)}C"],
    ["a backslash", "C\\C"],
    ["a closing script tag", "C</script><script>alert(1)</script>"],
    ["a comment opener before a script tag", "C<!--<script>"],
    ["a line break", "C\nC"],
  ])("hands %s to the parser as written", (_name, hostile) => {
    const drawer = fakeSmilesDrawer();
    const page = previewPageSandbox({ SmilesDrawer: drawer.SmilesDrawer });
    page.loadPage(buildSmilesDrawerPageHtml(LIBRARY));
    page.hand(smilesDrawerConfig(hostile, THEME));
    expect(drawer.parsed).toEqual([hostile]);
  });
});

describe("smilesDrawerConfig", () => {
  it("trims the SMILES and follows the theme", () => {
    expect(smilesDrawerConfig("  CCO \n", THEME)).toEqual({ smiles: "CCO", theme: "light", bg: "#ffffff" });
    expect(smilesDrawerConfig("CCO", { bg: "#101010", isDark: true })).toEqual({
      smiles: "CCO",
      theme: "dark",
      bg: "#101010",
    });
  });
});

describe("readSmilesDrawerError", () => {
  const message = (code: unknown) => JSON.stringify({ kind: SMILES_DRAWER_ERROR_KIND, code });

  it("reads the page's error codes", () => {
    expect(readSmilesDrawerError(message("render"))).toBe("render");
    expect(readSmilesDrawerError(message("unavailable"))).toBe("unavailable");
  });

  it("treats a code it does not know as a failed drawing", () => {
    expect(readSmilesDrawerError(message("something-new"))).toBe("render");
  });

  it.each([
    ["nothing", undefined],
    ["an empty string", ""],
    ["text that is not JSON", "hello"],
    ["JSON that is not an object", "42"],
    ["null", "null"],
    ["another kind of message", JSON.stringify({ kind: "loaded" })],
  ])("ignores %s", (_name, data) => {
    expect(readSmilesDrawerError(data)).toBeNull();
  });
});
