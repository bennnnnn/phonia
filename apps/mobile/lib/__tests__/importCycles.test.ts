/**
 * Structural guard: production code has no import cycles, counting type-only
 * and dynamic imports. ESLint's import/no-cycle skips type imports, and the
 * three cycles this replaced all closed through one.
 *
 * Resolves imports with the TypeScript compiler the app already builds with,
 * so `@/` paths resolve exactly as tsc resolves them.
 */
import * as ts from "typescript";

declare const __dirname: string;

const ROOT = ts.sys.resolvePath(`${__dirname}/../..`);
const PRODUCTION_DIRS = ["app", "components", "contexts", "features", "hooks", "lib", "ui"];

function productionFiles(): string[] {
  return PRODUCTION_DIRS.flatMap((dir) =>
    ts.sys.readDirectory(`${ROOT}/${dir}`, [".ts", ".tsx"], ["**/__tests__/**", "**/vendor/**"]),
  ).filter((file) => !file.endsWith(".d.ts"));
}

function importGraph(files: string[]): Map<string, string[]> {
  const { config } = ts.readConfigFile(`${ROOT}/tsconfig.json`, ts.sys.readFile);
  const options = ts.parseJsonConfigFileContent(config, ts.sys, ROOT).options;
  const cache = ts.createModuleResolutionCache(ROOT, (name) => name, options);
  const known = new Set(files);
  const graph = new Map<string, string[]>();
  for (const file of files) {
    const { importedFiles } = ts.preProcessFile(ts.sys.readFile(file) ?? "", true, true);
    const targets = importedFiles
      .map(
        ({ fileName }) =>
          ts.resolveModuleName(fileName, file, options, ts.sys, cache).resolvedModule
            ?.resolvedFileName,
      )
      .filter((target): target is string => target !== undefined && known.has(target));
    graph.set(file, [...new Set(targets)]);
  }
  return graph;
}

/** Strongly connected components with more than one file (Tarjan). */
function importCycles(graph: Map<string, string[]>): string[][] {
  const index = new Map<string, number>();
  const low = new Map<string, number>();
  const stack: string[] = [];
  const onStack = new Set<string>();
  const found: string[][] = [];
  const visit = (node: string): void => {
    index.set(node, index.size);
    low.set(node, index.get(node) ?? 0);
    stack.push(node);
    onStack.add(node);
    for (const target of graph.get(node) ?? []) {
      if (!index.has(target)) visit(target);
      if (onStack.has(target)) {
        low.set(node, Math.min(low.get(node) ?? 0, low.get(target) ?? 0));
      }
    }
    if (low.get(node) !== index.get(node)) return;
    const component: string[] = [];
    let member: string | undefined;
    do {
      member = stack.pop();
      if (member === undefined) break;
      onStack.delete(member);
      component.push(member);
    } while (member !== node);
    if (component.length > 1) found.push(component);
  };
  for (const node of graph.keys()) if (!index.has(node)) visit(node);
  return found;
}

describe("import graph", () => {
  const files = productionFiles();
  const graph = importGraph(files);

  it("finds a cycle when there is one", () => {
    const sample = new Map([
      ["a", ["b"]],
      ["b", ["c"]],
      ["c", ["a"]],
      ["d", ["a"]],
    ]);
    expect(importCycles(sample).map((cycle) => cycle.sort())).toEqual([["a", "b", "c"]]);
  });

  it("resolves the app's own imports, @/ paths included", () => {
    expect(files.length).toBeGreaterThan(500);
    expect(graph.get(`${ROOT}/lib/api.ts`)).toContain(`${ROOT}/features/chat/api.ts`);
  });

  it("has no import cycles in production code", () => {
    const cycles = importCycles(graph).map((cycle) =>
      cycle.map((file) => file.slice(ROOT.length + 1)).sort(),
    );
    expect(cycles).toEqual([]);
  });
});
