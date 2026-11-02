/**
 * Structural guard: small helpers the phone had copied keep one home (code-health audit
 * DUP-13). Six callers read a cancel their own way, three diagram parsers each kept a
 * validator kit for the server's limits, and two placed labels with their own overlap.
 * Four dollar and delimiter scanners each counted the backslashes before a character.
 * Five JSON readers each wrote out the same object check, and three readers of a
 * pipe table the same row test. Two Skia scenes each built a line path, and two a
 * path of separate strokes.
 */

import { appFiles, isTest, readSource, relative } from "@/lib/__tests__/support/sourceFiles";

const ONE_HOME: [string, RegExp, string][] = [
  ["reading a cancel by its name", /\.name\s*===?\s*["'](?:AbortError|CanceledError)["']/, "lib/api/abort.ts"],
  ["a fence parser's refusal error", /class \w+ extends Error \{\}/, "lib/fenceValidate.ts"],
  ["boxesOverlap", /function boxesOverlap\(/, "lib/physics/boxes.ts"],
  ["an odd backslash run escaping a character", /slashes % 2 === 1/, "lib/markdown/inlineCode.ts"],
  ["a pipe table row (looksLikePipeRow)", /startsWith\("\|"\) && \w+\.indexOf\("\|", 1\)/, "lib/markdown/streamTableHold.ts"],
  ["a Skia line or segments path", /function (?:linePath|segmentsPath)\(/, "components/rich/skia/paths.ts"],
  ["a JSON object check (isJsonRecord)", /typeof (\w+) === "object" &&[^\n]*!Array\.isArray\(\1\)/, "lib/jsonFence.ts"],
];

describe("shared helpers", () => {
  it.each(ONE_HOME)("%s lives only in its home", (_what, pattern, home) => {
    const found = appFiles()
      .filter((file) => !isTest(file) && pattern.test(readSource(file)))
      .map(relative);
    expect(found).toEqual([home]);
  });
});
