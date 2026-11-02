import {
  buildMermaidPageHtml,
  MERMAID_PAGE,
  mermaidPreviewConfig,
} from "@/lib/mermaidPreviewHtml";
import { PREVIEW_CSP } from "@/lib/preview/previewSandbox";

import { previewPageSandbox, settle } from "./fixtures/previewPageSandbox";

const LIGHT = { bg: "#FFFFFF", danger: "#D92D20", isDark: false };
const DARK = { bg: "#101010", danger: "#F97066", isDark: true };
const LIBRARY = "/*mermaid*/";

function fakeMermaid(run: () => Promise<void>) {
  return { initialize: jest.fn(), run: jest.fn(run) };
}

/**
 * Mermaid 10 as it behaves on a page: when its script loads it listens for the
 * window's load event and then draws every `.mermaid` node unless startOnLoad
 * is off by then; it never draws a node it has already tried, failed or not.
 */
function autoStartingMermaid() {
  let startOnLoad = true;
  const tried = new Set<unknown>();
  const drawn: string[] = [];
  const mermaid = {
    initialize: jest.fn((config: { startOnLoad?: boolean }) => {
      if (config.startOnLoad !== undefined) startOnLoad = config.startOnLoad;
    }),
    run: jest.fn(async ({ nodes }: { nodes: { textContent: string }[] }) => {
      for (const node of nodes) {
        if (tried.has(node)) continue;
        tried.add(node);
        if (!node.textContent) throw new Error("No diagram type detected");
        drawn.push(node.textContent);
      }
    }),
  };
  /** Its load listener on the page `html` builds, finding nodes by class. */
  function listen(page: ReturnType<typeof previewPageSandbox>, html: string) {
    page.window.addEventListener("load", () => {
      const nodes = /class="mermaid"/.test(html) ? [page.document.getElementById("diagram")] : [];
      if (startOnLoad) void mermaid.run({ nodes }).catch(() => undefined);
    });
  }
  return { mermaid, drawn, listen };
}

describe("buildMermaidPageHtml", () => {
  it("is one page for every diagram: the sandbox CSP, the library once, no diagram", () => {
    const html = MERMAID_PAGE.build({ mermaid: LIBRARY });
    expect(MERMAID_PAGE.libraries).toEqual(["mermaid"]);
    expect(html).toBe(buildMermaidPageHtml(LIBRARY));
    expect(html).toContain(`content="${PREVIEW_CSP}"`);
    expect(html).toContain("connect-src 'none'");
    expect(html.split(LIBRARY)).toHaveLength(2);
    expect(html).not.toContain(LIGHT.bg);
  });

  it("turns Mermaid's load-time auto-start off before the window loads", () => {
    const html = buildMermaidPageHtml(LIBRARY);
    const library = html.indexOf(LIBRARY);
    const noAutoStart = html.indexOf("<script>mermaid.initialize({ startOnLoad: false });</script>");
    expect(noAutoStart).toBeGreaterThan(library);
    expect(noAutoStart).toBeLessThan(html.indexOf("<body>"));
    // And it finds nothing to start: the diagram has no `mermaid` class.
    expect(html).not.toMatch(/class="mermaid"/);
  });

  it("draws a diagram that arrives after the window loaded (Android's late hand-off)", async () => {
    const fake = autoStartingMermaid();
    const page = previewPageSandbox({ mermaid: fake.mermaid });
    const html = buildMermaidPageHtml(LIBRARY);
    fake.listen(page, html);
    page.loadPage(html);
    page.fire("load");
    page.hand(mermaidPreviewConfig("graph TD; A-->B", LIGHT));
    await settle();
    page.runFrames();
    expect(fake.drawn).toEqual(["graph TD; A-->B"]);
    expect(page.posted).toEqual([{ kind: "mermaid-size", height: 116 }]);
  });

  it("keeps a closing script tag in the library from ending its script", () => {
    expect(buildMermaidPageHtml("var a = '</script>';")).toContain("var a = '<\\/script>';");
  });

  it("draws the diagram it is handed, in strict mode and the block's theme", async () => {
    const mermaid = fakeMermaid(() => Promise.resolve());
    const page = previewPageSandbox({ mermaid });
    page.loadPage(buildMermaidPageHtml(LIBRARY));
    expect(mermaid.run).not.toHaveBeenCalled();

    page.hand(mermaidPreviewConfig("  graph TD; A-->B  ", DARK));
    expect(page.elements.diagram.textContent).toBe("graph TD; A-->B");
    expect(page.css).toEqual({ "--bg": DARK.bg, "--danger": DARK.danger });
    expect(mermaid.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ startOnLoad: false, securityLevel: "strict", theme: "dark" }),
    );
    expect(mermaid.run).toHaveBeenCalledWith({ nodes: [page.elements.diagram] });

    await settle();
    page.runFrames();
    expect(page.posted).toEqual([{ kind: "mermaid-size", height: 116 }]);
  });

  it("fits a card's diagram to its width and draws the full-screen one at its own size", () => {
    const fitted = fakeMermaid(() => Promise.resolve());
    const card = previewPageSandbox({ mermaid: fitted });
    card.loadPage(buildMermaidPageHtml(LIBRARY));
    card.hand(mermaidPreviewConfig("erDiagram\n  A ||--o{ B : has", LIGHT));
    expect(fitted.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ er: { useMaxWidth: true }, sequence: { useMaxWidth: true } }),
    );

    const natural = fakeMermaid(() => Promise.resolve());
    const full = previewPageSandbox({ mermaid: natural });
    full.loadPage(buildMermaidPageHtml(LIBRARY));
    full.hand(mermaidPreviewConfig("erDiagram\n  A ||--o{ B : has", LIGHT, { natural: true }));
    expect(natural.initialize).toHaveBeenCalledWith(
      expect.objectContaining({
        flowchart: { useMaxWidth: false, htmlLabels: false },
        er: { useMaxWidth: false },
        sequence: { useMaxWidth: false },
      }),
    );
  });

  it("reports a diagram Mermaid cannot read", async () => {
    const page = previewPageSandbox({ mermaid: fakeMermaid(() => Promise.reject(new Error("Parse error"))) });
    page.loadPage(buildMermaidPageHtml(LIBRARY));
    page.hand(mermaidPreviewConfig("graph TD; A-->", LIGHT));
    await settle();
    expect(page.posted).toEqual([{ kind: "mermaid-error", message: "Parse error" }]);
    expect(page.elements.err.textContent).toBe("Diagram error: Parse error");
  });
});

describe("mermaidPreviewConfig", () => {
  it("names Mermaid's theme for the app's", () => {
    expect(mermaidPreviewConfig("graph TD; A-->B", LIGHT)).toEqual({
      source: "graph TD; A-->B",
      theme: "neutral",
      colors: { bg: LIGHT.bg, danger: LIGHT.danger },
      natural: false,
    });
    expect(mermaidPreviewConfig("graph TD; A-->B", DARK).theme).toBe("dark");
  });
});
