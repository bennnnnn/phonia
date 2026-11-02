import { normalizeMarkdownTables, preprocessMarkdown } from "@/lib/markdown/preprocess";
import { markdownItInstance } from "@/lib/markdown/parser";
import { preprocessMarkdownForStream } from "@/lib/markdown/preprocessStream";
import { IMPROPER_RESPONSE } from "./fixtures/improperIntegralResponse";

const negativeSide = String.raw`\lim_{a \to 0^{-}} \left(\ln|a| - \ln|-1|\right) = -\infty`;
const positiveSide = String.raw`\lim_{b \to 0^{+}} \left(\ln|1| - \ln|b|\right) = -\infty`;

it.each([
  [`\\(${negativeSide}\\)`, `\\(${positiveSide}\\)`],
  [`$${negativeSide}$`, `$${positiveSide}$`],
  [`\\[${negativeSide}\\]`, `\\[${positiveSide}\\]`],
  [`$$${negativeSide}$$`, `$$${positiveSide}$$`],
])("keeps absolute-value bars inside explicit math out of table repair", (first, second) => {
  const source = `- Both limits diverge:\n  - ${first}\n  - ${second}`;
  expect(normalizeMarkdownTables(source)).toBe(source);
});

it("preserves real table columns around parenthesized math without inventing extra columns", () => {
  const source = String.raw`Expression | Value
\(\ln|a| - \ln|-1|\) | -infinity`;
  const normalized = normalizeMarkdownTables(source);
  expect(normalized).toContain(String.raw`| \(\ln|a| - \ln|-1|\) | -infinity |`);
  expect(normalized.split("\n")[1]).toBe("| --- | --- |");
});

it("does not manufacture table rows in the exact persisted improper-integral response", () => {
  const prepared = preprocessMarkdown(IMPROPER_RESPONSE);
  const tokens = markdownItInstance.parse(prepared, {});
  expect(tokens.some((token) => token.type === "table_open")).toBe(false);
  expect(prepared).not.toMatch(/^\s*\|\s*---/m);
  expect(tokens.filter((token) => token.type === "list_item_open")).toHaveLength(4);
  expect(prepared).toContain("ln|a|");
  expect(prepared).toContain("ln|-1|");
});

it("keeps the completed streaming response free of invented table syntax", () => {
  const { prepared } = preprocessMarkdownForStream(IMPROPER_RESPONSE, null);
  expect(prepared).toBe(preprocessMarkdown(IMPROPER_RESPONSE));
  expect(prepared).not.toMatch(/^\s*\|\s*---/m);
});
