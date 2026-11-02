/**
 * Shrink-only guards: today's offenders are recorded in a JSON baseline beside the test,
 * none may be added or grow, and one that shrinks is locked in by rerunning the test with
 * its update variable set (as the API's `function_size_baseline.json` is).
 */
import * as ts from "typescript";

import { appFiles, isTest, readSource } from "./sourceFiles";

/** Production source, as `scripts/check_file_sizes.py` reads it: no tests, vendor or generated code. */
export function productionFiles(): string[] {
  return appFiles()
    .filter((file) => !isTest(file) && !/\.(d|generated)\.ts$/.test(file))
    .sort();
}

export function parseSource(file: string): ts.SourceFile {
  const kind = file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  return ts.createSourceFile(file, readSource(file), ts.ScriptTarget.Latest, true, kind);
}

/**
 * The recorded baseline. With `update` set in the environment it is first lowered to
 * `current` (the offenders today): an entry gone from `current` leaves, one that shrank
 * is recorded smaller, and nothing new is ever added.
 */
export function recordedBaseline(
  path: string,
  current: Record<string, number>,
  update: string,
): Record<string, number> {
  const baseline = JSON.parse(ts.sys.readFile(path) ?? "{}") as Record<string, number>;
  if (!process.env[update]) return baseline;
  const lowered = Object.fromEntries(
    Object.entries(baseline)
      .filter(([key]) => key in current)
      .map(([key, value]) => [key, Math.min(value, current[key])])
      .sort(([a], [b]) => (a < b ? -1 : 1)),
  );
  ts.sys.writeFile(path, `${JSON.stringify(lowered, null, 2)}\n`);
  return lowered;
}

/** Offenders new to the baseline or above their recorded value, and recorded ones now lower. */
export function compareWithBaseline(
  current: Record<string, number>,
  baseline: Record<string, number>,
): { added: string[]; grown: string[]; lower: string[] } {
  const added = Object.entries(current)
    .filter(([key]) => !(key in baseline))
    .map(([key, value]) => `${key}: ${value}`);
  const grown = Object.entries(current)
    .filter(([key, value]) => key in baseline && value > baseline[key])
    .map(([key, value]) => `${key}: ${baseline[key]} -> ${value}`);
  const lower = Object.entries(baseline)
    .filter(([key, value]) => (current[key] ?? 0) < value)
    .map(([key, value]) => `${key}: ${value} -> ${current[key] ?? "none"}`);
  return { added, grown, lower };
}
