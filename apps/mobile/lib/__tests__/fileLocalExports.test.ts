/**
 * Structural guard: an export is named by some other file.
 *
 * Fifty exported types and values were read only inside their own file (#1914
 * had cleared 35 more before that). An export nothing imports reads as public
 * API, so the next change keeps it compatible for callers that do not exist.
 * Drop `export` instead; add it back when a second file needs the name.
 */

import { appFiles, isTest, readSource, relative, rootFiles } from "@/lib/__tests__/support/sourceFiles";

/** Names Expo Router reads from a route file. */
const ROUTER_EXPORTS = new Set(["unstable_settings", "ErrorBoundary"]);

const DECLARATION =
  /^export\s+(?:declare\s+)?(?:async\s+)?(?:type|interface|const|let|function|class|enum)\s+([A-Za-z_$][\w$]*)/gm;
const WORD = /[A-Za-z_$][\w$]*/g;

describe("exports", () => {
  it("every exported declaration is named in another file", () => {
    const files = appFiles();
    const texts = new Map<string, string>();
    for (const file of [...files, ...rootFiles()]) texts.set(file, readSource(file));
    const filesByWord = new Map<string, Set<string>>();
    for (const [file, text] of texts) {
      for (const word of new Set(text.match(WORD) ?? [])) {
        const named = filesByWord.get(word) ?? new Set<string>();
        named.add(file);
        filesByWord.set(word, named);
      }
    }

    const fileLocal: string[] = [];
    for (const file of files) {
      if (isTest(file)) continue;
      const path = relative(file);
      for (const match of (texts.get(file) ?? "").matchAll(DECLARATION)) {
        const name = match[1];
        if (path.startsWith("app/") && ROUTER_EXPORTS.has(name)) continue;
        const named = filesByWord.get(name) ?? new Set<string>();
        if ([...named].every((other) => other === file)) fileLocal.push(`${path} ${name}`);
      }
    }
    expect(fileLocal).toEqual([]);
  });
});
