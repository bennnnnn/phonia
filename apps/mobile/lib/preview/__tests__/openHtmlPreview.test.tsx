import { writeAsStringAsync } from "expo-file-system/legacy";
import { openBrowserAsync } from "expo-web-browser";
import { Linking, Share } from "react-native";

import { darkTheme, lightTheme } from "@/lib/theme";

import { openHtmlInBrowser, shareHtmlPreview, wrapFullDocument } from "@/lib/preview/openHtmlPreview";
import { HTML_EXPORT_CSP } from "@/lib/preview/previewSandbox";

// openHtmlPreview pulls in expo-file-system (Share/export path) and
// expo-web-browser, whose native modules aren't linked in this jest env.
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));
jest.mock("expo-web-browser", () => ({
  openBrowserAsync: jest.fn(),
}));

describe("wrapFullDocument", () => {
  it("passes through a document that already has its own shell", () => {
    const doc = `<!DOCTYPE html><html><head></head><body><p>x</p></body></html>`;
    expect(wrapFullDocument(doc)).toBe(doc);
    expect(wrapFullDocument(doc, darkTheme)).toBe(doc);
  });

  it("defaults to a light canvas when no theme is given (system-browser export path)", () => {
    const out = wrapFullDocument("<p>hi</p>");
    expect(out).toContain("color: #111827");
    expect(out).toContain("background: #FFFFFF");
  });

  it("DS-01: threads dark-mode tokens so the in-app Run tab is not a white sheet", () => {
    const out = wrapFullDocument("<p>hi</p>", darkTheme);
    expect(out).toContain(`color: ${darkTheme.text}`);
    expect(out).toContain(`background: ${darkTheme.bg}`);
    expect(out).toContain(`border: 1px solid ${darkTheme.border}`);
    expect(out).toContain(`th { background: ${darkTheme.surface}`);
    // The light-only Tailwind palette must not leak into a dark preview.
    expect(out).not.toContain("#111827");
    expect(out).not.toContain("#E5E7EB");
    expect(out).not.toContain("#F1F5F9");
  });

  it("threads light-mode tokens when the light theme is active", () => {
    const out = wrapFullDocument("<p>hi</p>", lightTheme);
    expect(out).toContain(`color: ${lightTheme.text}`);
    expect(out).toContain(`background: ${lightTheme.bg}`);
  });

  it("uses the shared code font, not a one-off 'SF Mono'", () => {
    expect(wrapFullDocument("<p>hi</p>", darkTheme)).not.toContain("'SF Mono'");
  });
});

const DATA_URL_PREFIX = "data:text/html;charset=utf-8,";
const CSP_META = `<meta http-equiv="Content-Security-Policy" content="${HTML_EXPORT_CSP}">`;
/** What the exported document starts with: its charset, then its CSP. */
const EXPORT_HEAD = `<!DOCTYPE html><meta charset="utf-8">${CSP_META}`;
const UTF8_BOM = "\uFEFF";

/** The document "Open in browser" hands the system browser as a data: URL. */
async function openedDocument(html: string): Promise<string> {
  const open = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
  open.mockClear();
  await expect(openHtmlInBrowser(html)).resolves.toBe(true);
  const url = String(open.mock.calls[0]?.[0]);
  expect(url.startsWith(DATA_URL_PREFIX)).toBe(true);
  return decodeURIComponent(url.slice(DATA_URL_PREFIX.length));
}

/** The file Share writes and hands the share sheet, after its byte-order mark. */
async function sharedDocument(html: string): Promise<string> {
  jest.spyOn(Share, "share").mockResolvedValue({ action: Share.sharedAction });
  jest.mocked(writeAsStringAsync).mockClear();
  await expect(shareHtmlPreview(html)).resolves.toBe(true);
  const file = String(jest.mocked(writeAsStringAsync).mock.calls[0]?.[1]);
  expect(file.startsWith(UTF8_BOM)).toBe(true);
  return file.slice(UTF8_BOM.length);
}

/**
 * The charset and the CSP are the document's first elements: the parser puts
 * them in the head it opens, before anything else in the document can run or load.
 */
function expectCspInHead(doc: string): void {
  expect(doc.startsWith(EXPORT_HEAD)).toBe(true);
  expect(doc.split("Content-Security-Policy")).toHaveLength(2);
}

describe("exported HTML (Open in browser, Share)", () => {
  it.each([
    ["a fragment", "<p>hi</p>"],
    ["a full document", "<!DOCTYPE html><html><head><title>t</title></head><body>hi</body></html>"],
    ["body content before its <head>", "<!DOCTYPE html><html>hi<head><title>t</title></head><body></body></html>"],
  ])("carries the export CSP as the first element of its head: %s", async (_what, html) => {
    expectCspInHead(await openedDocument(html));
    expectCspInHead(await sharedDocument(html));
  });

  it("carries the CSP on the file path a large page takes, and when data: URLs are refused", async () => {
    jest.mocked(writeAsStringAsync).mockClear();
    jest.spyOn(Linking, "openURL").mockResolvedValue(true);
    await openHtmlInBrowser(`<p>${"x".repeat(130_000)}</p>`);
    const file = String(jest.mocked(writeAsStringAsync).mock.calls[0]?.[1]);
    expect(file.startsWith(UTF8_BOM)).toBe(true);
    expectCspInHead(file.slice(UTF8_BOM.length));

    jest.spyOn(Linking, "openURL").mockRejectedValue(new Error("no handler"));
    jest.mocked(openBrowserAsync).mockClear();
    await openHtmlInBrowser("<p>hi</p>");
    const url = String(jest.mocked(openBrowserAsync).mock.calls[0]?.[0]);
    expectCspInHead(decodeURIComponent(url.slice(DATA_URL_PREFIX.length)));
  });

  it("carries the CSP when the share sheet gets the HTML as text", async () => {
    jest.mocked(writeAsStringAsync).mockRejectedValueOnce(new Error("disk full"));
    const share = jest.spyOn(Share, "share").mockResolvedValue({ action: Share.sharedAction });
    share.mockClear();
    await shareHtmlPreview("<p>hi</p>");
    const content = share.mock.calls[0]?.[0];
    expectCspInHead(content && "message" in content ? String(content.message) : "");
  });

  // Each got through stripScripts into the exported document on main.
  it.each([
    ["&#106;", '<a href="&#106;avascript:alert(1)">x</a>', /href|avascript/i],
    ["&#x6A;", '<a href="&#x6A;avascript:alert(1)">x</a>', /href|avascript/i],
    ["&colon;", '<a href="javascript&colon;alert(1)">x</a>', /href|javascript/i],
    ["&#x09;", '<a href="jav&#x09;ascript:alert(1)">x</a>', /href|ascript/i],
    ["&Tab;", '<a href="jav&Tab;ascript:alert(1)">x</a>', /href|ascript/i],
    ["svg xlink:href", '<svg><a xlink:href="javascript:alert(1)"><text y="20">x</text></a></svg>', /href|javascript/i],
    ["svg use data:", '<svg><use xlink:href="data:image/svg+xml,%3Csvg%20id=%22x%22/%3E#x"/></svg>', /href|data:/i],
    ["mixed case", '<A HrEf="JaVaScRiPt:alert(1)">x</A>', /href|javascript/i],
    ["control characters", '<a href="\u0001 java\nscript:alert(1)">x</a>', /href|script:/i],
    ["handler without a space", '<img src="x"onerror="alert(1)">', /onerror/i],
    ["assembled <script>", '<scr onx="y"ipt>alert(1)</script>', /<script/i],
  ])("neutralises %s in the exported document", async (_name, html, gone) => {
    for (const doc of [await openedDocument(html), await sharedDocument(html)]) {
      expectCspInHead(doc);
      expect(doc.slice(EXPORT_HEAD.length)).not.toMatch(gone);
    }
  });

  // A file has no transport charset, so a browser reads the page's own <meta
  // charset>. ISO-2022-JP drops "ESC ( B", which joins "http-equ" and "iv" into a
  // pragma after the disarming already ran on the JS string. The byte-order mark
  // (and the utf-8 meta ahead of the page's) keep the file UTF-8 whatever it says.
  it("is read as UTF-8 whatever charset the page declares", async () => {
    const html =
      '<!DOCTYPE html><html><head><meta charset="iso-2022-jp">' +
      '<meta http-equ\u001b(Biv=refresh content="0;url=https://evil.example/"></head><body>x</body></html>';
    const doc = await sharedDocument(html);
    expect(doc.startsWith(EXPORT_HEAD)).toBe(true);
    expect(doc.indexOf('<meta charset="utf-8">')).toBeLessThan(doc.indexOf('charset="iso-2022-jp"'));
    expect(new TextDecoder("utf-8").decode(new TextEncoder().encode(doc))).not.toContain("http-equiv=refresh");
  });
});
