import {
  PREVIEW_PAGE_LINK_KIND,
  previewPageConfigScript,
  previewPageLink,
  previewPageStartScript,
} from "@/lib/preview/previewPage";

import { fakeAnchor, previewPageSandbox } from "@/lib/__tests__/fixtures/previewPageSandbox";

/** A page whose start function records each config it starts with. */
function recordingPage() {
  const received: unknown[] = [];
  const page = previewPageSandbox({ received });
  const html = `<script>${previewPageStartScript("function (config) { received.push(config); }")}</script>`;
  return { page, html, received };
}

describe("preview page handshake", () => {
  it("starts with the data handed in before the page script ran", () => {
    // iOS: injectedJavaScriptBeforeContentLoaded runs at document start.
    const { page, html, received } = recordingPage();
    page.hand({ source: "graph TD; A-->B" });
    expect(received).toEqual([]);
    page.loadPage(html);
    expect(received).toEqual([{ source: "graph TD; A-->B" }]);
  });

  it("starts when the data arrives after the page script ran", () => {
    // Android may run the first injection late; injectedJavaScript always follows the load.
    const { page, html, received } = recordingPage();
    page.loadPage(html);
    expect(received).toEqual([]);
    page.hand({ source: "graph LR; X-->Y" });
    expect(received).toEqual([{ source: "graph LR; X-->Y" }]);
  });

  it("starts once, however many times the data arrives", () => {
    const { page, html, received } = recordingPage();
    page.hand({ n: 1 });
    page.loadPage(html);
    page.hand({ n: 1 });
    page.hand({ n: 1 });
    expect(received).toEqual([{ n: 1 }]);
  });

  it.each([
    ["a closing script tag", "</script><script>alert(1)</script>"],
    ["a backtick and a template placeholder", "C`${alert(1)}`C"],
    ["quotes and backslashes", `"'\\"\\n`],
    ["line and paragraph separators", "a\u2028b\u2029c"],
    ["a comment opener", "<!--<script>"],
  ])("hands %s to the page unchanged", (_name, value) => {
    const page = previewPageSandbox();
    page.hand({ value, nested: { list: [value] } });
    expect(page.window.RECALL_PREVIEW).toEqual({ value, nested: { list: [value] } });
  });

  it("keeps the separators escaped in the script text", () => {
    const script = previewPageConfigScript({ value: "a\u2028b\u2029c" });
    expect(script).not.toMatch(/[\u2028\u2029]/);
    expect(script).toContain("a\\u2028b\\u2029c");
  });

  it("ends the injected script with a value the WebView can return", () => {
    expect(previewPageConfigScript({}).endsWith("true;")).toBe(true);
  });
});

describe("links on a preview page", () => {
  function linkPage() {
    const { page, html } = recordingPage();
    page.loadPage(html);
    return page;
  }
  const link = (url: string) => ({ kind: PREVIEW_PAGE_LINK_KIND, url });

  it("hands a tapped link to the app instead of following it", () => {
    const page = linkPage();
    const click = page.click(fakeAnchor("https://example.com/a?b=1"));
    expect(click.defaultPrevented).toBe(true);
    expect(page.posted).toEqual([link("https://example.com/a?b=1")]);
  });

  it("finds the link around what was tapped, SVG links included", () => {
    const page = linkPage();
    const anchor = fakeAnchor("https://example.com/node", { inSvg: true });
    const label = { nodeName: "tspan", parentNode: { nodeName: "text", parentNode: anchor } };
    expect(page.click(label).defaultPrevented).toBe(true);
    expect(page.posted).toEqual([link("https://example.com/node")]);
  });

  it("resolves a relative link against the page, so the app sees where it really goes", () => {
    const page = linkPage();
    page.click(fakeAnchor("secrets.json"));
    expect(page.posted).toEqual([link("file:///cache/preview-pages/secrets.json")]);
  });

  it("follows no link a script clicked on its own, and opens nothing for it", () => {
    const page = linkPage();
    expect(page.click(fakeAnchor("https://example.com"), { isTrusted: false }).defaultPrevented).toBe(true);
    expect(page.posted).toEqual([]);
  });

  it("leaves a tap outside any link alone", () => {
    const page = linkPage();
    expect(page.click({ nodeName: "rect", parentNode: null }).defaultPrevented).toBe(false);
    expect(page.posted).toEqual([]);
  });

  it("hands a window the page opens to the app instead", () => {
    const page = linkPage();
    const open = page.window.open as (url?: string) => unknown;
    expect(open("https://example.com/editor")).toBeNull();
    expect(open()).toBeNull();
    expect(page.posted).toEqual([link("https://example.com/editor")]);
  });
});

describe("previewPageLink", () => {
  it("reads a link message", () => {
    expect(previewPageLink(JSON.stringify({ kind: PREVIEW_PAGE_LINK_KIND, url: "https://x.test" }))).toBe(
      "https://x.test",
    );
  });

  it.each([
    ["nothing", undefined],
    ["text that is not JSON", "hello"],
    ["another kind of message", JSON.stringify({ kind: "mermaid-size", height: 100 })],
    ["a link without a URL", JSON.stringify({ kind: PREVIEW_PAGE_LINK_KIND, url: 42 })],
    ["null", "null"],
  ])("ignores %s", (_name, data) => {
    expect(previewPageLink(data)).toBeNull();
  });
});
