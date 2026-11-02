/**
 * Structural guard: what the phone evaluates at launch. Metro runs without
 * `inlineRequires`, so a module that loads evaluates every module it imports
 * statically (and every `require` that runs as it loads) right then;
 * `import()` and type-only imports wait. From the routes a launch loads,
 * follow those eager edges and keep the heavy code below out: each loads on
 * first use.
 *
 * A failure prints the import chain that pulled the module in. Load it with
 * `import()` where it is used (or `React.lazy`), or import only its types.
 */
import * as ts from "typescript";

declare const __dirname: string;

const ROOT = ts.sys.resolvePath(`${__dirname}/../..`);

/**
 * expo-router loads every layout at launch, then the screen it opens on: the
 * chat for a signed-in account, and sign-in, consent or onboarding otherwise.
 */
function launchEntries(): string[] {
  const layouts = ts.sys
    .readDirectory(`${ROOT}/app`, [".tsx", ".ts"])
    .filter((file) => /\/_layout\.tsx?$/.test(file))
    .map((file) => file.slice(ROOT.length + 1));
  return [...layouts, "app/index.tsx", "app/login.tsx", "app/consent.tsx", "app/onboarding.tsx"];
}

/** Packages that load on first use, never at launch. */
const LAZY_PACKAGES = [
  "katex",
  "mathjax-full",
  "@shopify/react-native-skia",
  "@sentry/react-native",
  "expo-print",
];

/** App modules that load on first use, never at launch. */
const LAZY_FILES = [
  // PDF export: KaTeX and its 360 KB stylesheet.
  "features/chat/model/printDocument.ts",
  "lib/vendor/katexCss.ts",
  // The math scanner: camera, live text detection, crop and review.
  "features/scanner/components/MathEquationScanner.tsx",
  // The photo viewer: pager, zoom, Download and Share, and the media library.
  "features/attachments/components/AttachmentImageViewer.tsx",
  // Live Talk: the WebRTC session, its turn state and chimes, and the overlay.
  "features/speech/model/realtimeVoice.ts",
  "features/speech/model/realtimeTurnState.ts",
  "features/speech/model/liveTalkSfx.ts",
  "features/speech/components/LiveTalkOverlay.tsx",
  // Physics scene parsers that size a placeholder, and the renderers.
  "lib/physics/simulation/index.ts",
  "components/rich/diagrams/spec.ts",
  "components/rich/FunctionGraphBlock.tsx",
  "components/rich/GeometryBlock.tsx",
];

const ASSET = /\.(ttf|otf|png|jpe?g|gif|webp|svg|wav|mp3|mp4)$/;

/** Specifiers a module evaluates as it loads, in source order. */
function eagerSpecifiers(fileName: string, source: string): string[] {
  const file = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, false);
  const found: string[] = [];
  for (const statement of file.statements) {
    if (ts.isImportDeclaration(statement)) {
      const clause = statement.importClause;
      const bindings = clause?.namedBindings;
      const typesOnly =
        clause?.isTypeOnly ||
        (clause !== undefined &&
          !clause.name &&
          bindings !== undefined &&
          ts.isNamedImports(bindings) &&
          bindings.elements.length > 0 &&
          bindings.elements.every((element) => element.isTypeOnly));
      if (!typesOnly && ts.isStringLiteral(statement.moduleSpecifier)) {
        found.push(statement.moduleSpecifier.text);
      }
    } else if (ts.isExportDeclaration(statement) && statement.moduleSpecifier) {
      const clause = statement.exportClause;
      const typesOnly =
        statement.isTypeOnly ||
        (clause !== undefined &&
          ts.isNamedExports(clause) &&
          clause.elements.length > 0 &&
          clause.elements.every((element) => element.isTypeOnly));
      if (!typesOnly && ts.isStringLiteral(statement.moduleSpecifier)) {
        found.push(statement.moduleSpecifier.text);
      }
    } else if (
      ts.isImportEqualsDeclaration(statement) &&
      !statement.isTypeOnly &&
      ts.isExternalModuleReference(statement.moduleReference) &&
      ts.isStringLiteral(statement.moduleReference.expression)
    ) {
      found.push(statement.moduleReference.expression.text);
    }
  }
  // A require() runs with the module outside a function body, or inside a
  // function the module calls as it loads, (() => { ... })().
  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node)) {
      let callee: ts.Expression = node.expression;
      while (ts.isParenthesizedExpression(callee)) callee = callee.expression;
      if (ts.isFunctionExpression(callee) || ts.isArrowFunction(callee)) {
        visit(callee.body);
        node.arguments.forEach(visit);
        return;
      }
      const [argument] = node.arguments;
      if (
        ts.isIdentifier(node.expression) &&
        node.expression.text === "require" &&
        node.arguments.length === 1 &&
        ts.isStringLiteral(argument)
      ) {
        found.push(argument.text);
      }
    }
    if (ts.isFunctionLike(node)) return;
    ts.forEachChild(node, visit);
  };
  ts.forEachChild(file, visit);
  return found.filter((specifier) => !ASSET.test(specifier));
}

function packageName(specifier: string): string {
  const parts = specifier.split("/");
  return specifier.startsWith("@") ? parts.slice(0, 2).join("/") : parts[0];
}

type LaunchGraph = {
  /** Each app file evaluated at launch, with the file that imported it first. */
  files: Map<string, string | null>;
  /** Each package evaluated at launch, with the file that imported it first. */
  packages: Map<string, string>;
};

function launchGraph(): LaunchGraph {
  const { config } = ts.readConfigFile(`${ROOT}/tsconfig.json`, ts.sys.readFile);
  const options = ts.parseJsonConfigFileContent(config, ts.sys, ROOT).options;
  const cache = ts.createModuleResolutionCache(ROOT, (name) => name, options);
  const files = new Map<string, string | null>();
  const packages = new Map<string, string>();
  const queue = launchEntries().map((entry) => `${ROOT}/${entry}`);
  for (const entry of queue) files.set(entry, null);
  for (let next = queue.shift(); next !== undefined; next = queue.shift()) {
    const importer = next;
    for (const specifier of eagerSpecifiers(importer, ts.sys.readFile(importer) ?? "")) {
      const resolved = ts.resolveModuleName(specifier, importer, options, ts.sys, cache)
        .resolvedModule?.resolvedFileName;
      const isAppFile =
        resolved !== undefined &&
        resolved.startsWith(`${ROOT}/`) &&
        !resolved.includes("/node_modules/") &&
        !resolved.endsWith(".d.ts") &&
        /\.(tsx?|js)$/.test(resolved);
      if (isAppFile) {
        if (!files.has(resolved)) {
          files.set(resolved, importer);
          queue.push(resolved);
        }
      } else if (!specifier.startsWith(".") && !specifier.startsWith("@/")) {
        const name = packageName(specifier);
        if (!packages.has(name)) packages.set(name, importer);
      }
    }
  }
  return { files, packages };
}

function relative(file: string): string {
  return file.slice(ROOT.length + 1);
}

function chain(graph: LaunchGraph, file: string | null): string[] {
  const links: string[] = [];
  for (let at = file; at; at = graph.files.get(at) ?? null) links.unshift(relative(at));
  return links;
}

describe("launch imports", () => {
  const graph = launchGraph();

  it("follows static imports, re-exports and top-level requires, not import() or types", () => {
    const source = [
      'import "side-effect";',
      'import type { A } from "type-only";',
      'import { type B } from "inline-types";',
      'import C, { type D } from "value";',
      'export { E } from "re-export";',
      'export type { F } from "type-re-export";',
      'const G = require("top-level-require");',
      'const icon = require("./icon.png");',
      'const lazy = () => import("dynamic");',
      'function later() { return require("in-function"); }',
      'import H = require("import-equals");',
      'import type I = require("import-equals-type");',
      'const J = (() => require("immediately-invoked"))();',
      '(function () { require("immediately-invoked-function"); })();',
      'const K = () => (() => require("invoked-later"))();',
    ].join("\n");
    expect(eagerSpecifiers("sample.ts", source)).toEqual([
      "side-effect",
      "value",
      "re-export",
      "import-equals",
      "top-level-require",
      "immediately-invoked",
      "immediately-invoked-function",
    ]);
  });

  it("starts from every layout and each screen a launch can open on", () => {
    const entries = launchEntries();
    expect(entries).toEqual(expect.arrayContaining([
      "app/_layout.tsx",
      "app/settings/_layout.tsx",
      "app/memory/_layout.tsx",
      "app/index.tsx",
      "app/login.tsx",
      "app/consent.tsx",
      "app/onboarding.tsx",
    ]));
  });

  it("reaches the modules the first screen draws", () => {
    expect(graph.files.has(`${ROOT}/contexts/AuthContext.tsx`)).toBe(true);
    expect(graph.files.has(`${ROOT}/features/chat/screens/ChatScreen.tsx`)).toBe(true);
    expect(graph.packages.has("react-native")).toBe(true);
  });

  it("keeps heavy code out of launch", () => {
    const loaded = [
      ...LAZY_PACKAGES.filter((name) => graph.packages.has(name)).map((name) =>
        [...chain(graph, graph.packages.get(name) ?? null), name].join(" -> "),
      ),
      ...LAZY_FILES.filter((file) => graph.files.has(`${ROOT}/${file}`)).map((file) =>
        chain(graph, `${ROOT}/${file}`).join(" -> "),
      ),
    ];
    expect(loaded).toEqual([]);
  });
});
