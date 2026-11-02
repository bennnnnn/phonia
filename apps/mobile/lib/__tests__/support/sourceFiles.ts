/**
 * The app's own source files, for the structural guards that read them.
 *
 * The lib jest project pins `types: ["jest"]` and @types/node is not installed, so the
 * node shapes this needs are declared here.
 */

declare const __dirname: string;
// eslint-disable-next-line @typescript-eslint/no-require-imports -- @types/node is not installed, so node:fs is required untyped
const fs = require("node:fs") as {
  readdirSync: (path: string) => string[];
  readFileSync: (path: string, encoding: "utf8") => string;
  statSync: (path: string) => { isDirectory: () => boolean };
};

/** apps/mobile, spelled without ".." so test paths are recognisable. */
export const ROOT = __dirname.split("/").slice(0, -3).join("/");
const SOURCE_DIRS = ["app", "components", "features", "lib", "hooks", "contexts", "ui"];
/** Vendored code keeps upstream exports; installed packages are not ours. */
const SKIPPED_DIRS = new Set(["node_modules", "vendor"]);

export function readSource(path: string): string {
  return fs.readFileSync(path, "utf8");
}

function filesUnder(dir: string): string[] {
  let names: string[];
  try {
    names = fs.readdirSync(dir);
  } catch {
    return [];
  }
  return names.flatMap((name: string) => {
    const path = `${dir}/${name}`;
    if (fs.statSync(path).isDirectory()) {
      return SKIPPED_DIRS.has(name) ? [] : filesUnder(path);
    }
    return /\.tsx?$/.test(name) ? [path] : [];
  });
}

export function isTest(path: string): boolean {
  return path.includes("/__tests__/") || /\.test\.tsx?$/.test(path);
}

/** Every .ts/.tsx file of the app's source folders, tests included. */
export function appFiles(): string[] {
  return SOURCE_DIRS.flatMap((dir) => filesUnder(`${ROOT}/${dir}`));
}

/** Root-level config and setup files (jest mocks, say). */
export function rootFiles(): string[] {
  return fs
    .readdirSync(ROOT)
    .filter((name: string) => /\.(t|j)sx?$/.test(name))
    .map((name: string) => `${ROOT}/${name}`);
}

/** `file` relative to apps/mobile. */
export function relative(file: string): string {
  return file.slice(ROOT.length + 1);
}
