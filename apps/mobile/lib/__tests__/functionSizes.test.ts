/**
 * Structural guard: a function may run to 100 lines; a longer one may only shrink, as
 * the API's `test_function_sizes.py` holds for the server.
 *
 * Every function over the limit (declarations, methods, arrow functions, components and
 * the callbacks inside them) is recorded in `functionSizeBaseline.json` at its length: it
 * may not grow, and no new one may join. Split a long one by step (read, decide, render);
 * after a split, rerun with `UPDATE_FUNCTION_SIZES=1` to lower the recorded lengths and
 * drop functions back under the limit.
 *
 * A function is named by where it sits: `ChatScreen`, `ChatScreen.onSend`,
 * `ChatScreen.useEffect()`, `Store.load`. Long ones sharing a name in one file are
 * numbered in source order (`useEffect()`, `useEffect()#2`), each held at its own length.
 */
import * as ts from "typescript";

import { relative } from "./support/sourceFiles";
import {
  compareWithBaseline,
  parseSource,
  productionFiles,
  recordedBaseline,
} from "./support/ratchet";

declare const __dirname: string;

const LIMIT = 100;
const BASELINE = `${__dirname}/functionSizeBaseline.json`;

function hasBody(node: ts.Node): node is ts.FunctionLikeDeclaration {
  return ts.isFunctionLike(node) && "body" in node && node.body !== undefined;
}

/** The function's own name, or the name of what holds it. */
function ownName(node: ts.FunctionLikeDeclaration): string {
  if (ts.isConstructorDeclaration(node)) return "constructor";
  if (node.name && !ts.isComputedPropertyName(node.name)) return node.name.getText();
  let holder: ts.Node = node.parent;
  while (ts.isParenthesizedExpression(holder) || ts.isAsExpression(holder)) holder = holder.parent;
  // `const Row = memo((props) => …)` and `const onSend = useCallback(() => …)` take the name.
  if (ts.isCallExpression(holder) && ts.isVariableDeclaration(holder.parent)) holder = holder.parent;
  if (
    ts.isVariableDeclaration(holder) ||
    ts.isPropertyAssignment(holder) ||
    ts.isPropertyDeclaration(holder)
  ) {
    return holder.name.getText();
  }
  if (ts.isJsxExpression(holder) && ts.isJsxAttribute(holder.parent)) {
    return holder.parent.name.getText();
  }
  if (ts.isCallExpression(holder)) {
    const callee = holder.expression;
    if (ts.isIdentifier(callee)) return `${callee.text}()`;
    if (ts.isPropertyAccessExpression(callee)) return `${callee.name.text}()`;
  }
  if (ts.isExportAssignment(holder)) return "default";
  return "<anonymous>";
}

function qualifiedName(node: ts.FunctionLikeDeclaration): string {
  const names = [ownName(node)];
  for (let parent = node.parent; !ts.isSourceFile(parent); parent = parent.parent) {
    if (hasBody(parent)) names.unshift(ownName(parent));
    else if (ts.isClassLike(parent)) names.unshift(parent.name?.text ?? "<class>");
  }
  return names.join(".");
}

/** Qualified name -> lines, for every function in `source`. */
function functionLengths(source: ts.SourceFile): [string, number][] {
  const found: [string, number][] = [];
  const visit = (node: ts.Node): void => {
    if (hasBody(node)) {
      const start = source.getLineAndCharacterOfPosition(node.getStart(source)).line;
      const end = source.getLineAndCharacterOfPosition(node.getEnd()).line;
      found.push([qualifiedName(node), end - start + 1]);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

/**
 * Name -> lines for the functions over the limit, in source order. Long functions that
 * share a name are numbered (`useEffect()`, `useEffect()#2`) so each one is held; short
 * ones never take a number, so adding a small effect renames nothing.
 */
function overLimit(lengths: [string, number][]): Record<string, number> {
  const seen: Record<string, number> = {};
  const long: Record<string, number> = {};
  for (const [name, lines] of lengths) {
    if (lines <= LIMIT) continue;
    seen[name] = (seen[name] ?? 0) + 1;
    long[seen[name] === 1 ? name : `${name}#${seen[name]}`] = lines;
  }
  return long;
}

/** `file::qualified.name` -> lines, for every production function over the limit. */
function longFunctions(): Record<string, number> {
  const sizes: Record<string, number> = {};
  for (const file of productionFiles()) {
    for (const [name, lines] of Object.entries(overLimit(functionLengths(parseSource(file))))) {
      sizes[`${relative(file)}::${name}`] = lines;
    }
  }
  return sizes;
}

describe("function sizes", () => {
  const sizes = longFunctions();
  const { added, grown, lower } = compareWithBaseline(
    sizes,
    recordedBaseline(BASELINE, sizes, "UPDATE_FUNCTION_SIZES"),
  );

  it("names a function by where it sits", () => {
    const source = ts.createSourceFile(
      "x.tsx",
      [
        "export function Screen() {",
        "  const onSend = useCallback(() => {}, []);",
        "  useEffect(() => {",
        "  }, []);",
        "  return <B onPress={() => {}} />;",
        "}",
        "const Row = memo((props: P) => null);",
        "class Store { load() {} }",
      ].join("\n"),
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TSX,
    );
    expect(functionLengths(source)).toEqual([
      ["Screen", 6],
      ["Screen.onSend", 1],
      ["Screen.useEffect()", 2],
      ["Screen.onPress", 1],
      ["Row", 1],
      ["Store.load", 1],
    ]);
  });

  it("holds each long function that shares a name", () => {
    const lengths: [string, number][] = [
      ["Screen.useEffect()", 140],
      ["Screen.useEffect()", 3],
      ["Screen.useEffect()", 120],
      ["Screen", 300],
    ];
    expect(overLimit(lengths)).toEqual({
      "Screen.useEffect()": 140,
      "Screen.useEffect()#2": 120,
      Screen: 300,
    });
  });

  it(`lets no function over ${LIMIT} lines join or grow`, () => {
    // Over the limit: split it by step (read, decide, render) instead of recording it.
    expect({ added, grown }).toEqual({ added: [], grown: [] });
  });

  it("records the current lengths", () => {
    // Shorter now: rerun with UPDATE_FUNCTION_SIZES=1 to lock it in.
    expect(lower).toEqual([]);
  });
});
