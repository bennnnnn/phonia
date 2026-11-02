import { decodeAttributeEntities } from "@/lib/preview/htmlEntities";

describe("decodeAttributeEntities", () => {
  it.each([
    // Numeric, decimal and hex, with and without the `;`, any case, leading zeros.
    ["&#106;avascript:", "javascript:"],
    ["&#106avascript:", "javascript:"],
    ["&#0000106;avascript:", "javascript:"],
    ["&#x6A;avascript:", "javascript:"],
    ["&#X6a;avascript:", "javascript:"],
    ["&#x6A avascript:", "j avascript:"],
    ["jav&#x09;ascript:", "jav\tascript:"],
    ["jav&#9ascript:", "jav\tascript:"],
    ["java&#10;script:", "java\nscript:"],
    // Hex digits are read greedily: `&#x6Aa` is U+06AA, not "ja".
    ["&#x6Aavascript", "ڪvascript"],
    // Named references that decode to ASCII.
    ["javascript&colon;alert(1)", "javascript:alert(1)"],
    ["jav&Tab;ascript:", "jav\tascript:"],
    ["jav&NewLine;ascript:", "jav\nascript:"],
    ["data:text&sol;html", "data:text/html"],
    ["&lpar;&rpar;&comma;&period;&semi;&equals;", "(),.;="],
    ["&fjlig;", "fj"],
    // Legacy names without `;`, unless `=` or an alphanumeric follows (attribute rule).
    ["a&ampb", "a&ampb"],
    ["a&amp b", "a& b"],
    ["?x=1&lt=2", "?x=1&lt=2"],
    ["&lt:&gt", "<:>"],
    ["&QUOT;&AMP;", '"&'],
    // Out-of-range, NUL and surrogate code points become U+FFFD; C1 maps to Windows-1252.
    ["&#0;", "�"],
    ["&#x110000;", "�"],
    ["&#xD800;", "�"],
    ["&#99999999999999999999;", "�"],
    ["&#x80;&#x9F;&#x81;", "€Ÿ\u0081"],
    // Not references: left exactly as written.
    ["&colon", "&colon"],
    ["&Tab", "&Tab"],
    ["&#;", "&#;"],
    ["&#x;", "&#x;"],
    ["& x", "& x"],
    ["&unknown;", "&unknown;"],
    ["a&&#106;", "a&j"],
  ])("decodes %j as %j", (input, expected) => {
    expect(decodeAttributeEntities(input)).toBe(expected);
  });

  it("leaves plain text untouched", () => {
    expect(decodeAttributeEntities("https://example.com/?q=1")).toBe("https://example.com/?q=1");
  });
});
