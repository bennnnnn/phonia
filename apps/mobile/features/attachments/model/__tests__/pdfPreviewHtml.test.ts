import * as pdfPage from "@/features/attachments/model/pdfPreviewHtml";
import { buildPdfPreviewHtml, PDF_LIBRARIES } from "@/features/attachments/model/pdfPreviewHtml";
import { PDF_PREVIEW_CSP, PREVIEW_VIEWPORT } from "@/lib/preview/previewSandbox";
import type { Theme } from "@/lib/theme";

const theme = { bg: "#FFFFFF", text: "#111113", danger: "#D92D20" } as Theme;
const SOURCES = { pdf: "/*pdf.js*/", pdfWorker: "/*pdf.js worker*/" };

function pageCsp(html: string): string {
  const csp = /<meta http-equiv="Content-Security-Policy" content="([^"]*)">/.exec(html)?.[1];
  if (csp === undefined) throw new Error("The page has no CSP.");
  return csp;
}

describe("buildPdfPreviewHtml", () => {
  it("uses the shared zoomable viewport", () => {
    const html = buildPdfPreviewHtml("AAAA", theme, false, SOURCES);
    expect(html).toContain(`content="${PREVIEW_VIEWPORT}"`);
    expect(html).not.toContain("maximum-scale");
  });

  it("carries the PDF inline as inert base64 text, beside the page mode and colors", () => {
    const html = buildPdfPreviewHtml("QU JD\r\nRA==", theme, true, SOURCES);
    expect(html).toContain('<script type="application/pdf" id="pdf-data">QU JD\r\nRA==</script>');
    expect(html).toContain('"allPages":true');
    expect(html).toContain('"bg":"#FFFFFF"');
    // The bytes are never JavaScript: not in the config the page runs.
    expect(html).not.toContain('"data":');
  });

  it("refuses text that is not base64: the page's markup holds it as is", () => {
    for (const bad of ["QUJD</script><script>alert(1)</script>", "QUJD<!--", "QUJD&amp;", "QUJD\"'"]) {
      expect(() => buildPdfPreviewHtml(bad, theme, false, SOURCES)).toThrow();
    }
  });

  it("loads under a policy that fetches nothing: no file, no network", () => {
    const html = buildPdfPreviewHtml("QUJD", theme, false, SOURCES);
    const csp = pageCsp(html);
    expect(csp).toBe(PDF_PREVIEW_CSP);
    // A meta CSP binds only what follows it: it leads the head, before any script.
    expect(html.indexOf('http-equiv="Content-Security-Policy"')).toBeLessThan(html.indexOf("<script"));
    expect(html.match(/http-equiv="Content-Security-Policy"/g)).toHaveLength(1);
    expect(csp).toContain("connect-src 'none'");
    expect(csp).not.toMatch(/file:|https?:|\*/);
  });

  it("reads no file and asks for nothing: the PDF is the page's own text", () => {
    const html = buildPdfPreviewHtml("QUJD", theme, true, SOURCES);
    expect(html).not.toMatch(/XMLHttpRequest|fetch\(|cfg\.src|file:/);
  });

  it("runs pdf.js and keeps its worker inert until the page spawns it from a Blob", () => {
    expect(PDF_LIBRARIES).toEqual(["pdf", "pdfWorker"]);
    const html = buildPdfPreviewHtml("QUJD", theme, false, SOURCES);
    expect(html).toContain(`<script>${SOURCES.pdf}</script>`);
    expect(html).toContain(`<script type="text/pdf-worker" id="pdf-worker-src">${SOURCES.pdfWorker}</script>`);
  });

  it("draws every page lazily for the viewer and page 1 for the card", () => {
    const html = buildPdfPreviewHtml("QUJD", theme, true, SOURCES);
    expect(html).toContain("IntersectionObserver");
    expect(html).toContain("cfg.allPages");
  });

  it("loads the PDF with eval-compiled fonts off", () => {
    const html = buildPdfPreviewHtml("QUJD", theme, false, SOURCES);
    expect(html).toContain("getDocument({ data: bytes, isEvalSupported: false })");
  });

  it("hands pdf.js the bytes of its own PDF text, then drops the text", async () => {
    // "%PDF-", as the page carries it.
    const html = buildPdfPreviewHtml("JVBE\nRi0=", theme, false, SOURCES);
    const start = html.lastIndexOf("<script>") + "<script>".length;
    const body = html.slice(start, html.indexOf("</script>", start));
    const removed: unknown[] = [];
    const dataTag = {
      textContent: /id="pdf-data">([^<]*)<\/script>/.exec(html)![1],
      parentNode: { removeChild: (node: unknown) => removed.push(node) },
    };
    const elements: Record<string, unknown> = {
      err: { textContent: "", style: {} },
      pages: { appendChild: () => undefined },
      "pdf-worker-src": { textContent: SOURCES.pdfWorker },
      "pdf-data": dataTag,
    };
    const getDocument = jest.fn(() => ({ promise: new Promise(() => undefined) }));
    const page = {
      window: { RECALL_PDF: { allPages: false, colors: {} }, innerWidth: 320, devicePixelRatio: 2 },
      document: { documentElement: { style: { setProperty: () => undefined } }, getElementById: (id: string) => elements[id] },
      pdfjsLib: { GlobalWorkerOptions: {} as { workerSrc?: string }, getDocument },
      URL: { createObjectURL: () => "blob:worker" },
      Blob: class {},
    };
    new Function(...Object.keys(page), body)(...Object.values(page));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(getDocument).toHaveBeenCalledWith({
      data: new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]),
      isEvalSupported: false,
    });
    expect(page.pdfjsLib.GlobalWorkerOptions.workerSrc).toBe("blob:worker");
    expect(removed).toEqual([dataTag]);
  });

  it("ships a page script that parses", () => {
    const html = buildPdfPreviewHtml("QUJD", theme, false, SOURCES);
    const start = html.lastIndexOf("<script>") + "<script>".length;
    const body = html.slice(start, html.indexOf("</script>", start));
    expect(() => new Function(body)).not.toThrow();
  });
});

describe("pdfPreviewHtml exports", () => {
  it("offer no page that may read files", () => {
    // A PDF is untrusted: no policy or page from this module opens file: to it.
    for (const [name, value] of Object.entries(pdfPage)) {
      if (typeof value === "string") expect([name, value]).toEqual([name, expect.not.stringMatching(/file:/)]);
    }
  });
});
