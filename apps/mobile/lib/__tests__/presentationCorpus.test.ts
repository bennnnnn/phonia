/**
 * docs/fixtures/presentation_cases.json is shared with the API test
 * (app/tests/modules/chat/test_presentation.py): the server presents a reply
 * before it is saved, the phone presents the text still streaming and rows
 * saved before the server did. Both must give every input the same output.
 */
import { preprocessMarkdown } from "@/lib/markdown/preprocess";
import { preprocessMarkdownForStream } from "@/lib/markdown/preprocessStream";
import {
  isServerPresentedRow,
  presentAssistantMarkdown,
  presentStreamTail,
  SERVER_PRESENTATION_CUTOVER,
} from "@/lib/markdown/presentation";

import fixture from "../../../../docs/fixtures/presentation_cases.json";

type PresentationCase = {
  id: string;
  area: string;
  input: string;
  expected: string;
  note?: string;
};

const CASES: PresentationCase[] = fixture.cases;
const PRESENTED = { presented: true };
const byId = (id: string): PresentationCase => {
  const found = CASES.find((c) => c.id === id);
  if (!found) throw new Error(`no presentation case ${id}`);
  return found;
};

describe("presentation corpus", () => {
  it.each(CASES.map((c) => [c.id, c] as const))("%s presents as the server does", (_id, c) => {
    expect(presentAssistantMarkdown(c.input)).toBe(c.expected);
  });

  it.each(CASES.map((c) => [c.id, c] as const))("%s presents to itself once presented", (_id, c) => {
    expect(presentAssistantMarkdown(c.expected)).toBe(c.expected);
  });
});

describe("streaming presentation", () => {
  it("streams closed prose and calculation rows the way they settle", () => {
    const sources = [
      byId("bold-glued-train").input,
      byId("bold-glued-cyclist").input,
      byId("bold-punctuation-stays-tight").input,
      `${byId("equals-chain").input}\n`,
      byId("paren-chain-across-lines").input,
    ];
    for (const source of sources) {
      expect(preprocessMarkdownForStream(source, null).prepared).toBe(preprocessMarkdown(source));
    }
    const partial = preprocessMarkdownForStream("at**40", null).prepared;
    expect(partial).toBe("at**40");
    expect(partial).toBe(presentAssistantMarkdown("at**40"));
  });

  it("wraps a bare fraction on the streaming tail and leaves an open fence alone", () => {
    const wrapped = presentStreamTail(String.raw`half is \frac{1}{2}`);
    expect(wrapped).toContain(String.raw`$\frac{1}{2}$`);
    expect(wrapped).not.toMatch(/(?:^|[^$])\\frac/);
    const openFence = presentStreamTail(String.raw`see` + "\n```\n\\frac{1}{2}\n");
    expect(openFence.startsWith("see")).toBe(true);
    expect(openFence).toContain("```\n\\frac{1}{2}\n");
    expect(openFence).not.toContain("$\\frac");
    expect(preprocessMarkdownForStream(String.raw`half is \frac{1}{2}`, null).prepared).toBe(wrapped);
    const openDollar = presentStreamTail(String.raw`$\frac{1}{2}`);
    expect(openDollar).toBe(String.raw`$\frac{1}{2}`);
    expect(openDollar).not.toContain("$$");
    expect(presentStreamTail(String.raw`see \(\frac{1}`)).toBe(String.raw`see \(\frac{1}`);
  });
});

/**
 * A saved row the server presented skips the phone's prose repairs. Every
 * corpus output must render, settled and in stream layout, exactly as it did
 * with the phone presenting it again: the change is invisible on server text.
 */
describe("a saved row the server presented", () => {
  it.each(CASES.map((c) => [c.id, c] as const))("%s renders as before", (_id, c) => {
    expect(preprocessMarkdown(c.expected, undefined, PRESENTED)).toBe(preprocessMarkdown(c.expected));
    expect(preprocessMarkdownForStream(c.expected, null, undefined, PRESENTED).prepared).toBe(
      preprocessMarkdownForStream(c.expected, null).prepared,
    );
  });

  it("keeps the saved prose as the server saved it", () => {
    expect(preprocessMarkdown("Turn at**40 km/h**.", undefined, PRESENTED)).toBe("Turn at**40 km/h**.");
    expect(preprocessMarkdown("Turn at**40 km/h**.")).toBe("Turn at **40 km/h**.");
    expect(presentStreamTail("at**40 km/h**", true)).toBe("at**40 km/h**");
  });

  it("still lays out the maths blocks the phone builds from it", () => {
    const rows = "$v = d/t$  \n$v = 50/10$  \n$v = 5$";
    for (const id of ["display-block-plain-chain", "bracket-line-plain-chain", "tilde-fence-left-alone"]) {
      const saved = byId(id).expected;
      expect(saved).not.toContain(rows);
      expect(preprocessMarkdown(saved, undefined, PRESENTED)).toBe(preprocessMarkdown(saved));
    }
    expect(preprocessMarkdown(byId("display-block-plain-chain").expected, undefined, PRESENTED)).toContain(
      rows,
    );
    expect(presentStreamTail(String.raw`half is \frac{1}{2}`, true)).toContain(String.raw`$\frac{1}{2}$`);
  });
});

describe("isServerPresentedRow", () => {
  const id = "0192f5c4-6f1e-7c3a-9a55-0c2f3e4d5a6b";
  it("starts at the cut-over", () => {
    expect(new Date(SERVER_PRESENTATION_CUTOVER).toISOString()).toBe("2026-11-16T00:00:00.000Z");
  });

  it.each([
    [id, "2026-11-16T00:00:00Z", true],
    [id, "2027-02-01T09:30:00.123456Z", true],
    [id, "2026-11-15T23:59:59.999999+00:00", false],
    [id, "2026-10-01T12:00:00Z", false],
    ["streaming", "2027-01-01T00:00:00Z", false],
    ["streamed-1798761600000", "2027-01-01T00:00:00Z", false],
    [id, "not a date", false],
  ])("%s saved at %s: %s", (rowId, createdAt, expected) => {
    expect(isServerPresentedRow({ id: rowId, created_at: createdAt })).toBe(expected);
  });
});
