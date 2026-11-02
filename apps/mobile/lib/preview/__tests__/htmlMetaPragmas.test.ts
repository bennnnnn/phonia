import { disarmMetaPragmas } from "@/lib/preview/htmlMetaPragmas";

const KEEP = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'">`;
const REFRESH = `<meta/http-equiv=refresh content="0;url=https://evil.example/">`;

/** "http-equiv" where an attribute name can start: a browser could read it as a pragma. */
function pragmaNames(html: string): number {
  return (html.match(/(?<![\w-])http-equiv/gi) ?? []).length;
}

describe("disarmMetaPragmas", () => {
  it("renames the attribute and deletes nothing, so no text around it can join", () => {
    const html = `<scr${REFRESH}ipt>alert(1)</script><p title="a>b">x</p>`;
    const out = disarmMetaPragmas(html);
    expect(pragmaNames(out)).toBe(0);
    expect(out.replaceAll("data-blocked-", "")).toBe(html);
    expect(out).not.toMatch(/<script/i);
  });

  it("returns a document with no pragma unchanged", () => {
    const html = '<meta charset="utf-8"><meta name="viewport" content="width=device-width">';
    expect(disarmMetaPragmas(html)).toBe(html);
  });

  it("keeps only the tag that is exactly `keep`", () => {
    const loosened = KEEP.replace("'none'", "*");
    const out = disarmMetaPragmas(`${KEEP}${loosened}${REFRESH}`, KEEP);
    expect(out.startsWith(KEEP)).toBe(true);
    expect(pragmaNames(out)).toBe(1);
  });

  it("stays linear on thousands of overlapping tags and still disarms every pragma", () => {
    // Each unclosed "<meta" reads to the end of the text; reading them all one by
    // one took seconds. Past the budget every name-shaped http-equiv is renamed.
    const hostile = "<meta/a=".repeat(15_000) + " " + "<meta ".repeat(20_000);
    const html = `${KEEP}${hostile}<!-- <meta title=' -->${REFRESH}'`;
    const started = Date.now();
    const out = disarmMetaPragmas(html, KEEP);
    expect(Date.now() - started).toBeLessThan(1_000);
    expect(out.startsWith(KEEP)).toBe(true);
    expect(pragmaNames(out)).toBe(1);
  });
});
