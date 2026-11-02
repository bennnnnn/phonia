/**
 * Code is drawn with ligatures off (`CODE_FACE`): Space Mono joins "fi" and
 * "fl", so `fib` read as "ﬁb". A style that names the code font by itself
 * brings the ligatures back, so none may.
 */
// The lib jest project has no @types/node (see libLayout.test.ts), and no
// react-native: CODE_FACE itself is checked in components/__tests__/CodeBlock.test.tsx.
declare const __dirname: string;
// eslint-disable-next-line @typescript-eslint/no-require-imports -- @types/node is not installed, so node:fs is required untyped
const { readdirSync, readFileSync, statSync } = require("node:fs") as {
  readdirSync: (path: string) => string[];
  readFileSync: (path: string, encoding: "utf8") => string;
  statSync: (path: string) => { isDirectory: () => boolean };
};

const ROOT = `${__dirname}/../..`;
const SOURCE_DIRS = ["app", "components", "features", "lib", "ui"];
const ALLOWED = new Set([
  "lib/fonts.ts", // CODE_FACE itself
  // react-native-render-html (the dev-only static preview) drops font variants it does not list.
  "components/StaticHtmlPreview.tsx",
]);

/** Source files under `dir`, relative to the app root; tests and vendored code left out. */
function sourceFiles(dir: string): string[] {
  return readdirSync(`${ROOT}/${dir}`).flatMap((name) => {
    const path = `${dir}/${name}`;
    if (statSync(`${ROOT}/${path}`).isDirectory()) {
      return name === "__tests__" || name === "vendor" ? [] : sourceFiles(path);
    }
    return /\.tsx?$/.test(name) ? [path] : [];
  });
}

describe("code text", () => {
  it("styles code with CODE_FACE, never the bare code font", () => {
    const bare = SOURCE_DIRS.flatMap(sourceFiles)
      .filter((path) => !ALLOWED.has(path))
      .filter((path) => /fontFamily:\s*CODE_FONT\b/.test(readFileSync(`${ROOT}/${path}`, "utf8")));
    expect(bare).toEqual([]);
  });
});
