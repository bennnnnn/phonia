/**
 * Structural guards for worklets, the functions that run on the UI thread.
 *
 * A worklet's default parameter reads nothing from outside the function, and a worklet
 * names nothing declared later in its file.
 *
 * The worklets compiler copies to the UI thread only what a worklet's body uses. A default
 * like `inset = ARROW_EDGE_INSET` is evaluated there with the constant missing, so it throws
 * "Property 'ARROW_EDGE_INSET' doesn't exist", and an error on the frame loop ends the app:
 * every moving physics scene crashed Expo Go on its first frame. Jest runs worklets on the
 * JS thread, where the constant is in scope, so no component test could see it.
 */
import * as ts from "typescript";

declare const __dirname: string;

const ROOT = ts.sys.resolvePath(`${__dirname}/../..`);
const PRODUCTION_DIRS = ["app", "components", "contexts", "features", "hooks", "lib", "ui"];
/** Globals the UI runtime has as well. */
const SAFE_GLOBALS = new Set(["undefined", "NaN", "Infinity", "Math", "Number"]);

function productionFiles(): string[] {
  return PRODUCTION_DIRS.flatMap((dir) =>
    ts.sys.readDirectory(`${ROOT}/${dir}`, [".ts", ".tsx"], ["**/__tests__/**", "**/vendor/**"]),
  ).filter((file) => !file.endsWith(".d.ts"));
}

function isWorklet(node: ts.SignatureDeclaration): boolean {
  const body = (node as ts.FunctionLikeDeclaration).body;
  const first = body && ts.isBlock(body) ? body.statements[0] : undefined;
  return Boolean(
    first &&
      ts.isExpressionStatement(first) &&
      ts.isStringLiteral(first.expression) &&
      first.expression.text === "worklet",
  );
}

/** The names a default value reads: not property names, object keys or types. */
function namesRead(initializer: ts.Expression): string[] {
  const names: string[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isTypeNode(node)) return;
    if (ts.isIdentifier(node)) {
      const { parent } = node;
      const isPropertyName =
        (ts.isPropertyAccessExpression(parent) && parent.name === node) ||
        (ts.isPropertyAssignment(parent) && parent.name === node);
      if (!isPropertyName) names.push(node.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(initializer);
  return names;
}

/** Every default value in a parameter, including ones inside a destructuring pattern. */
function defaultsIn(param: ts.ParameterDeclaration): ts.Expression[] {
  const found: ts.Expression[] = param.initializer ? [param.initializer] : [];
  const visit = (node: ts.Node): void => {
    if (ts.isBindingElement(node) && node.initializer) found.push(node.initializer);
    ts.forEachChild(node, visit);
  };
  visit(param.name);
  return found;
}

function boundNames(name: ts.BindingName): string[] {
  if (ts.isIdentifier(name)) return [name.text];
  return name.elements.flatMap((element) =>
    ts.isOmittedExpression(element) ? [] : boundNames(element.name),
  );
}

function outsideReads(file: string): string[] {
  const source = ts.createSourceFile(file, ts.sys.readFile(file) ?? "", ts.ScriptTarget.Latest, true);
  const problems: string[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isFunctionLike(node) && isWorklet(node)) {
      // An earlier parameter is in scope on the UI thread too.
      const earlier = new Set<string>();
      for (const param of node.parameters) {
        for (const value of defaultsIn(param)) {
          for (const name of namesRead(value)) {
            if (earlier.has(name) || SAFE_GLOBALS.has(name)) continue;
            const { line } = source.getLineAndCharacterOfPosition(param.getStart());
            problems.push(`${file.slice(ROOT.length + 1)}:${line + 1} ${param.getText()}`);
          }
        }
        boundNames(param.name).forEach((name) => earlier.add(name));
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return problems;
}

/** Module-level names a worklet uses that are declared after it in the same file. */
function laterNames(file: string): string[] {
  const source = ts.createSourceFile(file, ts.sys.readFile(file) ?? "", ts.ScriptTarget.Latest, true);
  const declared = new Map<string, number>();
  for (const statement of source.statements) {
    if (ts.isFunctionDeclaration(statement) && statement.name) {
      declared.set(statement.name.text, statement.getStart());
    }
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        if (ts.isIdentifier(declaration.name)) declared.set(declaration.name.text, statement.getStart());
      }
    }
  }
  const problems: string[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isFunctionLike(node) && isWorklet(node)) {
      const at = node.getStart();
      const { line } = source.getLineAndCharacterOfPosition(at);
      const named = new Set<string>();
      const scan = (inner: ts.Node): void => {
        if (ts.isIdentifier(inner) && (declared.get(inner.text) ?? -1) > at) {
          const { parent } = inner;
          const isPropertyName =
            (ts.isPropertyAccessExpression(parent) && parent.name === inner) ||
            (ts.isPropertyAssignment(parent) && parent.name === inner);
          if (!isPropertyName) named.add(inner.text);
        }
        ts.forEachChild(inner, scan);
      };
      const body = (node as ts.FunctionLikeDeclaration).body;
      if (body) scan(body);
      named.forEach((name) => problems.push(`${file.slice(ROOT.length + 1)}:${line + 1} uses ${name}`));
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return problems;
}

describe("worklets name only what is declared before them", () => {
  it("in every production file", () => {
    // A worklet captures what it names when it is made; a helper declared below it is
    // still undefined then. The label placement threw "overlapsAny is not a function".
    expect(productionFiles().flatMap(laterNames)).toEqual([]);
  });

  it("catches a worklet that calls a helper declared after it", () => {
    const file = `${ROOT}/lib/__tests__/__worklet_order_probe__.ts`;
    const original = ts.sys.readFile;
    const probe = [
      'export function place(a: number): number { "worklet"; return clear(a) + EDGE; }',
      'function clear(a: number): number { "worklet"; return a; }',
      "const EDGE = 6;",
      'export function fine(a: number): number { "worklet"; return clear(a) + EDGE; }',
    ].join("\n");
    ts.sys.readFile = (path, encoding) => (path === file ? probe : original(path, encoding));
    try {
      expect(laterNames(file)).toEqual([
        "lib/__tests__/__worklet_order_probe__.ts:1 uses clear",
        "lib/__tests__/__worklet_order_probe__.ts:1 uses EDGE",
      ]);
    } finally {
      ts.sys.readFile = original;
    }
  });
});

describe("worklet default parameters", () => {
  it("read only literals and earlier parameters", () => {
    // Move the value into the body instead: `chrome?: Inset` then `const inset = chrome ?? ZERO_INSET`.
    expect(productionFiles().flatMap(outsideReads)).toEqual([]);
  });

  it("catches a default that reads a module value", () => {
    const file = `${ROOT}/lib/__tests__/__worklet_default_probe__.ts`;
    const original = ts.sys.readFile;
    const probe = [
      "const EDGE = 6;",
      'export function fit(a: number, edge = EDGE, b = a, { c = EDGE } = {}): number { "worklet"; return a + edge + b + c; }',
      'export function plain(edge = EDGE): number { return edge; }',
    ].join("\n");
    ts.sys.readFile = (path, encoding) => (path === file ? probe : original(path, encoding));
    try {
      expect(outsideReads(file)).toEqual([
        "lib/__tests__/__worklet_default_probe__.ts:2 edge = EDGE",
        "lib/__tests__/__worklet_default_probe__.ts:2 { c = EDGE } = {}",
      ]);
    } finally {
      ts.sys.readFile = original;
    }
  });
});
