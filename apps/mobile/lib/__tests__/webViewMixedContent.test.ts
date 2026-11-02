/**
 * No WebView lets a page load http: content into an https: one. Android's
 * WebView refuses mixed content unless `mixedContentMode` says otherwise
 * (react-native-webview leaves it at MIXED_CONTENT_NEVER_ALLOW), so no WebView
 * may set it to anything but "never". The HTML Run tab set "always".
 */
// The lib jest project has no @types/node (see libLayout.test.ts).
declare const __dirname: string;
// eslint-disable-next-line @typescript-eslint/no-require-imports -- @types/node is not installed, so node:fs is required untyped
const { readdirSync, readFileSync, statSync } = require("node:fs") as {
  readdirSync: (path: string) => string[];
  readFileSync: (path: string, encoding: "utf8") => string;
  statSync: (path: string) => { isDirectory: () => boolean };
};

const ROOT = `${__dirname}/../..`;
const SOURCE_DIRS = ["app", "components", "contexts", "features", "hooks", "lib", "ui"];
const LOOSER_THAN_NEVER = /mixedContentMode\s*[=:]\s*(?!["']never["'])/;

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

describe("WebView mixed content", () => {
  it("is never allowed", () => {
    const looser = SOURCE_DIRS.flatMap(sourceFiles).filter((path) =>
      LOOSER_THAN_NEVER.test(readFileSync(`${ROOT}/${path}`, "utf8")),
    );
    expect(looser).toEqual([]);
  });
});
