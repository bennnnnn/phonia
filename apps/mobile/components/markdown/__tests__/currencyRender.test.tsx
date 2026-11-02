/**
 * Currency on screen. Stored replies from 2026-10-25 drew "38.40 =" in the
 * maths font, dropped dollar signs and ended list items in ".:". Each one
 * must read exactly as written, settled or streaming, whether the server
 * presented it or the phone does.
 */
import { cleanup, render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";

jest.mock("@/components/LinkPreviewCard", () => ({ LinkPreviewCard: "LinkPreviewCard" }));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));
jest.mock("@/components/WebPreviewCodeBlock", () => ({ WebPreviewCodeBlock: "WebPreviewCodeBlock" }));
jest.mock("@/components/rich/CircularClockBlock", () => ({ CircularClockBlock: "CircularClockBlock" }));

/** The stored reply, and what a reader sees of it (bullets and bold marks aside). */
const REPLY = [
  "Here is the budget.",
  "",
  "*   **Accommodation:** $50–$80/night for hostels or basic B&Bs = $ 350–$560 for 7 nights.",
  "*   **Food:** $30/day for local spots, street food, and groceries = $ 210.",
  "",
  "Half of $38.40 = $ 19.20, plus the $12 from last week = $ 31.20.",
].join("\n");
const SEEN = [
  "Here is the budget.",
  "Accommodation: $50–$80/night for hostels or basic B&Bs = $ 350–$560 for 7 nights.",
  "Food: $30/day for local spots, street food, and groceries = $ 210.",
  "Half of $38.40 = $ 19.20, plus the $12 from last week = $ 31.20.",
].join("");

const CARET = "▏";

function textOf(node: unknown): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  const children = (node as { children?: unknown[] }).children ?? [];
  return children.map(textOf).join("");
}

async function seen(content: string, presented: boolean, streaming: boolean): Promise<string> {
  const screen = await render(
    <MarkdownContent content={content} presented={presented} streaming={streaming} />,
  );
  const text = textOf(screen.toJSON()).split(CARET).join("");
  await cleanup();
  return text;
}

describe("currency in a reply", () => {
  it.each([
    [false, false],
    [true, false],
    [false, true],
  ])("reads as written (presented %s, streaming %s)", async (presented, streaming) => {
    expect(await seen(REPLY, presented, streaming)).toBe(SEEN);
  });

  it.each([
    [String.raw`- Hotel: $80 \times 7 = $560`, "Hotel: $80 × 7 = $560"],
    [String.raw`Total: $80 \cdot 7 = $560 for the week.`, "Total: $80 ⋅ 7 = $560 for the week."],
    [String.raw`$2 \times $3 = $6`, "$2 × $3 = $6"],
  ])("shows money worked with TeX as text: %s", async (source, text) => {
    for (const streaming of [false, true]) expect(await seen(source, false, streaming)).toBe(text);
  });

  it.each([
    [String.raw`$1,200 \times 12 = $14,400`, "$1,200 × 12 = $14,400"],
    [String.raw`$2x = 10$, so x costs \$5$.`, "2x = 10, so x costs $5."],
  ])("keeps the whole amount: %s", async (source, text) => {
    for (const streaming of [false, true]) {
      expect((await seen(source, false, streaming)).replace(/\u00a0/g, " ")).toBe(text);
    }
  });

  it("draws a formula after a price as maths, and no TeX source, while it streams", async () => {
    const source = String.raw`It costs $5, and $4! = 4 \times 3 \times 2 \times 1 = 24$.`;
    const drawn = "It costs $5, and 4! = 4 × 3 × 2 × 1 = 24.";
    const shown: string[] = [];
    for (let cut = 1; cut <= source.length; cut += 1) {
      const text = await seen(source.slice(0, cut), false, true);
      if (/\\|times|[\uE000-\uE00F]/.test(text)) shown.push(`at ${cut}: ${text}`);
    }
    expect(shown).toEqual([]);
    for (const streaming of [false, true]) {
      expect((await seen(source, false, streaming)).replace(/\u00a0/g, " ")).toBe(drawn);
    }
  });

  it("keeps every dollar while the reply streams in", async () => {
    const off: string[] = [];
    for (let cut = 1; cut < REPLY.length; cut += 7) {
      // A bold label still being written shows its `**` until it closes.
      const text = (await seen(REPLY.slice(0, cut), false, true)).replace(/\*/g, "");
      if (!SEEN.startsWith(text)) off.push(`at ${cut}: ${text}`);
    }
    expect(off).toEqual([]);
  });
});
