/**
 * Structural guard: code fences are read with one grammar (`lib/mdFenceScan.ts`).
 *
 * Line loops flipped a flag on every ``` line, regexes closed a fence on the first
 * ``` anywhere, and seven files wrote the closer rule out again, so a ``` shown inside
 * a ~~~ block turned the rest of a reply inside out (code-health audit DUP-03). Read
 * markers with `readFenceMarker`, walk `scanFences` / `fencedLines` / `fenceAfterLine`,
 * or close with `closesFence`.
 */

import { appFiles, isTest, readSource, relative } from "@/lib/__tests__/support/sourceFiles";

const OWNER = "lib/mdFenceScan.ts";

/** `file: line` → why that line may read a fence by hand. */
const ALLOWED: Record<string, string> = {
  'lib/markdown/preprocessTables.ts: if (line.startsWith("```", i)) {':
    "drops a ```lang token left inside a table cell; no fence is read",
  "lib/math/pasteNormalize.ts: return trimmed.replace(/```math\\n([\\s\\S]*?)```/gi, (_m, body: string) => {":
    "the user's paste in the composer, where a closer glued to the last line still ends it",
};

const HAND_READS = [
  // A fence line tested by its first characters.
  /\.startsWith\(\s*["'`](?:```|~~~)/,
  // A regex anchored on a fence line: /^```/, /^(?:```|~~~)/, /^\s*```/.
  /\/\^(?:\\s\*|\[ \\t\]\*)?\(?(?:\?:)?(?:```|~~~)/,
  // A regex spanning a whole fence, which closes on the first ``` anywhere.
  /\/[^/\n]*```[^\n]*```[^\n]*\/[gimsuy]*/,
  // The closer rule written out again.
  /\.char\s*===\s*\w+\.char/,
];

/** The trimmed code lines (not comments) that read a fence by hand. */
function handReads(text: string): string[] {
  return text.split("\n").flatMap((line) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("//") || trimmed.startsWith("*") || trimmed.startsWith("/*")) return [];
    return HAND_READS.some((pattern) => pattern.test(line)) ? [trimmed] : [];
  });
}

function productionReads(): string[] {
  return appFiles()
    .filter((file) => !isTest(file) && relative(file) !== OWNER)
    .flatMap((file) => handReads(readSource(file)).map((line) => `${relative(file)}: ${line}`));
}

describe("one fence grammar", () => {
  it("sees a hand-written fence read", () => {
    expect(handReads('if (line.trimStart().startsWith("```")) inFence = !inFence;')).toHaveLength(1);
    expect(handReads("const FENCE = /^(?:```|~~~)/;")).toHaveLength(1);
    expect(handReads("text.replace(/```math\\n([\\s\\S]*?)```/g, '')")).toHaveLength(1);
    expect(handReads("if (marker.char === open.char) open = null;")).toHaveLength(1);
    expect(handReads("// a line that starts with ``` opens a fence")).toEqual([]);
  });

  it("no production code reads a fence by hand", () => {
    expect(productionReads().filter((entry) => !(entry in ALLOWED))).toEqual([]);
  });

  it("every allowance still applies", () => {
    const reads = new Set(productionReads());
    expect(Object.keys(ALLOWED).filter((entry) => !reads.has(entry))).toEqual([]);
  });
});
