/**
 * Reading a file's catches for the two shrink-only catch guards: catches that do nothing
 * (`emptyCatches.test.ts`) and catches that do something but drop the error unseen
 * (`swallowedCatches.test.ts`). A catch is counted by at most one of them.
 */
import * as ts from "typescript";

import { ROOT, relative } from "./sourceFiles";
import { parseSource, productionFiles } from "./ratchet";

/** Library no-ops a handler may be named by (`noop`, `_.noop`). */
const NO_OP_NAMES = new Set(["noop"]);

const ASSIGNMENTS = new Set([
  ts.SyntaxKind.EqualsToken, ts.SyntaxKind.PlusEqualsToken, ts.SyntaxKind.MinusEqualsToken,
  ts.SyntaxKind.AsteriskEqualsToken, ts.SyntaxKind.AsteriskAsteriskEqualsToken, ts.SyntaxKind.SlashEqualsToken,
  ts.SyntaxKind.PercentEqualsToken, ts.SyntaxKind.LessThanLessThanEqualsToken,
  ts.SyntaxKind.GreaterThanGreaterThanEqualsToken, ts.SyntaxKind.GreaterThanGreaterThanGreaterThanEqualsToken,
  ts.SyntaxKind.AmpersandEqualsToken, ts.SyntaxKind.BarEqualsToken, ts.SyntaxKind.CaretEqualsToken,
  ts.SyntaxKind.BarBarEqualsToken, ts.SyntaxKind.AmpersandAmpersandEqualsToken,
  ts.SyntaxKind.QuestionQuestionEqualsToken,
]);

/** A call, `new`, assignment, `++`/`--`, `await`, `yield` or `delete` in `node`, outside nested functions. */
function hasEffect(node: ts.Node): boolean {
  if (ts.isFunctionLike(node)) return false;
  if (
    ts.isCallExpression(node) || ts.isNewExpression(node) || ts.isTaggedTemplateExpression(node) ||
    ts.isAwaitExpression(node) || ts.isYieldExpression(node) || ts.isDeleteExpression(node) ||
    (ts.isBinaryExpression(node) && ASSIGNMENTS.has(node.operatorToken.kind)) ||
    ((ts.isPrefixUnaryExpression(node) || ts.isPostfixUnaryExpression(node)) &&
      (node.operator === ts.SyntaxKind.PlusPlusToken || node.operator === ts.SyntaxKind.MinusMinusToken))
  ) {
    return true;
  }
  return ts.forEachChild(node, hasEffect) === true;
}

/** `undefined` or `void x` with no effect: an expression that is nothing. */
function isNothing(node: ts.Expression): boolean {
  if (ts.isParenthesizedExpression(node)) return isNothing(node.expression);
  return (ts.isIdentifier(node) && node.text === "undefined") || (ts.isVoidExpression(node) && !hasEffect(node));
}

/** A statement that does nothing: no call, assignment or throw, and no `return` of a value. */
function isInert(statement: ts.Statement): boolean {
  if (ts.isEmptyStatement(statement) || ts.isContinueStatement(statement) || ts.isBreakStatement(statement)) {
    return true;
  }
  if (ts.isBlock(statement)) return statement.statements.every(isInert);
  if (ts.isExpressionStatement(statement)) return !hasEffect(statement.expression);
  if (ts.isReturnStatement(statement)) return !statement.expression || isNothing(statement.expression);
  if (ts.isIfStatement(statement)) {
    return !hasEffect(statement.expression) && isInert(statement.thenStatement) &&
      (!statement.elseStatement || isInert(statement.elseStatement));
  }
  return false;
}

type FunctionNode = ts.ArrowFunction | ts.FunctionExpression | ts.FunctionDeclaration;

const isFunctionNode = (node: ts.Node): node is FunctionNode =>
  ts.isArrowFunction(node) || ts.isFunctionExpression(node) || ts.isFunctionDeclaration(node);

/** A function whose body does nothing, or whose expression body is nothing. */
function doesNothing(node: ts.Node): boolean {
  if (!isFunctionNode(node)) return false;
  const body = node.body;
  if (!body) return false;
  return ts.isBlock(body) ? body.statements.every(isInert) : isNothing(body);
}

const hasModifier = (node: ts.Node, kind: ts.SyntaxKind): boolean =>
  ts.canHaveModifiers(node) && Boolean(ts.getModifiers(node)?.some((modifier) => modifier.kind === kind));

/** Names this file gives to functions that do nothing (`const ignore = () => undefined`), and which it exports. */
function localNoOps(source: ts.SourceFile): { names: Set<string>; exported: Set<string> } {
  const names = new Set<string>();
  const exported = new Set<string>();
  const visit = (node: ts.Node): void => {
    if (ts.isFunctionDeclaration(node) && doesNothing(node)) {
      if (node.name) names.add(node.name.text);
      if (hasModifier(node, ts.SyntaxKind.ExportKeyword)) {
        exported.add(hasModifier(node, ts.SyntaxKind.DefaultKeyword) || !node.name ? "default" : node.name.text);
      }
    }
    if (ts.isVariableStatement(node)) {
      for (const declaration of node.declarationList.declarations) {
        if (!ts.isIdentifier(declaration.name) || !declaration.initializer || !doesNothing(declaration.initializer)) {
          continue;
        }
        names.add(declaration.name.text);
        if (hasModifier(node, ts.SyntaxKind.ExportKeyword)) exported.add(declaration.name.text);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return { names, exported };
}

/** Finds the file a module specifier names (`@/lib/x`, `./x`), or undefined outside the app. */
export type Resolve = (specifier: string, from: string) => ts.SourceFile | undefined;

const moduleText = (node: ts.Expression | undefined): string | undefined =>
  node && ts.isStringLiteral(node) ? node.text : undefined;

/** The names `source` exports for functions that do nothing, through its own re-exports too. */
function exportedNoOps(source: ts.SourceFile, resolve: Resolve, seen = new Set<string>()): Set<string> {
  if (seen.has(source.fileName)) return new Set();
  seen.add(source.fileName);
  const { names, exported } = localNoOps(source);
  for (const node of source.statements) {
    if (!ts.isExportDeclaration(node)) continue;
    const from = moduleText(node.moduleSpecifier);
    const target = from ? resolve(from, source.fileName) : undefined;
    if (from && !target) continue;
    const theirs = target ? exportedNoOps(target, resolve, seen) : names;
    if (!node.exportClause) {
      for (const name of theirs) if (name !== "default") exported.add(name);
    } else if (ts.isNamedExports(node.exportClause)) {
      for (const element of node.exportClause.elements) {
        if (theirs.has((element.propertyName ?? element.name).text)) exported.add(element.name.text);
      }
    }
  }
  return exported;
}

/** Local names `source` imports for functions that do nothing (`import { ignore as skip }`). */
function importedNoOps(source: ts.SourceFile, resolve: Resolve): Set<string> {
  const names = new Set<string>();
  for (const node of source.statements) {
    if (!ts.isImportDeclaration(node) || !node.importClause) continue;
    const from = moduleText(node.moduleSpecifier);
    const target = from ? resolve(from, source.fileName) : undefined;
    if (!target) continue;
    const theirs = exportedNoOps(target, resolve);
    const { name, namedBindings } = node.importClause;
    if (name && theirs.has("default")) names.add(name.text);
    if (namedBindings && ts.isNamedImports(namedBindings)) {
      for (const element of namedBindings.elements) {
        if (theirs.has((element.propertyName ?? element.name).text)) names.add(element.name.text);
      }
    }
  }
  return names;
}

function isNoOpHandler(node: ts.Expression | undefined, noOps: Set<string>): boolean {
  if (!node) return false;
  if (ts.isIdentifier(node)) return NO_OP_NAMES.has(node.text) || noOps.has(node.text);
  if (ts.isPropertyAccessExpression(node)) return NO_OP_NAMES.has(node.name.text);
  return doesNothing(node);
}

/** The rejection handler of `p.catch(h)`, `p["catch"](h)` or `p.then(ok, h)`, if `node` is one of those calls. */
function rejectionHandler(node: ts.Node): ts.Expression | undefined {
  if (!ts.isCallExpression(node)) return undefined;
  const callee = node.expression;
  const method = ts.isPropertyAccessExpression(callee)
    ? callee.name.text
    : ts.isElementAccessExpression(callee) && ts.isStringLiteralLike(callee.argumentExpression)
      ? callee.argumentExpression.text
      : undefined;
  if (method === "catch") return node.arguments[0];
  if (method === "then") return node.arguments[1];
  return undefined;
}

const noOpNames = (source: ts.SourceFile, resolve: Resolve): Set<string> =>
  new Set([...localNoOps(source).names, ...importedNoOps(source, resolve)]);

/** Catch clauses and rejection handlers that do nothing, in `source`. */
export function emptyCatches(source: ts.SourceFile, resolve: Resolve = () => undefined): number {
  const noOps = noOpNames(source, resolve);
  let count = 0;
  const visit = (node: ts.Node): void => {
    if (ts.isCatchClause(node) && node.block.statements.every(isInert)) count += 1;
    if (isNoOpHandler(rejectionHandler(node), noOps)) count += 1;
    ts.forEachChild(node, visit);
  };
  visit(source);
  return count;
}

/** Sentry's SDK, and the app's reporter over it (`lib/sentry.ts`). */
const isReporterModule = (specifier: string, target: ts.SourceFile | undefined): boolean =>
  specifier === "@sentry/react-native" || Boolean(target?.fileName.endsWith("/lib/sentry.ts"));

/** Local names `source` imports from a reporter module: its functions, or the module itself (`* as Sentry`). */
function reporterNames(source: ts.SourceFile, resolve: Resolve): Set<string> {
  const names = new Set<string>();
  for (const node of source.statements) {
    if (!ts.isImportDeclaration(node) || !node.importClause || node.importClause.isTypeOnly) continue;
    const from = moduleText(node.moduleSpecifier);
    if (!from || !isReporterModule(from, resolve(from, source.fileName))) continue;
    const { name, namedBindings } = node.importClause;
    if (name) names.add(name.text);
    if (namedBindings && ts.isNamespaceImport(namedBindings)) names.add(namedBindings.name.text);
    if (namedBindings && ts.isNamedImports(namedBindings)) {
      for (const element of namedBindings.elements) if (!element.isTypeOnly) names.add(element.name.text);
    }
  }
  return names;
}

/** Sentry's own capture calls, by whatever object they are reached through. */
const CAPTURE_CALLS = new Set(["captureException", "captureMessage"]);

/** A call that reports: `console.*` (a logger), Sentry's capture, or anything imported from a reporter module. */
function isReportCall(node: ts.CallExpression, reporters: Set<string>): boolean {
  const callee = node.expression;
  if (ts.isIdentifier(callee)) return reporters.has(callee.text) || CAPTURE_CALLS.has(callee.text);
  if (!ts.isPropertyAccessExpression(callee)) return false;
  const owner = callee.expression;
  if (ts.isIdentifier(owner) && (owner.text === "console" || reporters.has(owner.text))) return true;
  return CAPTURE_CALLS.has(callee.name.text);
}

/** The names a catch binds its error to (`catch (e)`, `catch ({ code })`, a handler's first parameter). */
function boundNames(binding: ts.BindingName | undefined): string[] {
  if (!binding) return [];
  if (ts.isIdentifier(binding)) return [binding.text];
  return binding.elements.flatMap((element) =>
    ts.isOmittedExpression(element) ? [] : boundNames(element.name),
  );
}

/**
 * Whether `body` lets the failure be seen: it names the error (passes it on, logs it,
 * reads it), throws, or calls a reporter. A throw inside a nested function is not this
 * catch's; a report or a use of the error anywhere in it is.
 */
function letsFailureOut(body: ts.Node, errorNames: string[], reporters: Set<string>): boolean {
  const names = new Set(errorNames);
  const visit = (node: ts.Node, nested: boolean): boolean => {
    if (ts.isThrowStatement(node) && !nested) return true;
    if (ts.isIdentifier(node) && names.has(node.text)) return true;
    if (ts.isCallExpression(node) && isReportCall(node, reporters)) return true;
    const inner = nested || ts.isFunctionLike(node);
    return ts.forEachChild(node, (child) => visit(child, inner)) === true;
  };
  return visit(body, false);
}

/** A rejection handler that drops the error: a function that neither lets it out nor is a no-op. */
function swallowsRejection(handler: ts.Expression | undefined, reporters: Set<string>): boolean {
  if (!handler || !(ts.isArrowFunction(handler) || ts.isFunctionExpression(handler))) return false;
  const errorNames = boundNames(handler.parameters[0]?.name);
  return !doesNothing(handler) && !letsFailureOut(handler.body, errorNames, reporters);
}

/**
 * Catch clauses and rejection handlers that do something but drop the error: they
 * return or set a fallback, and nothing reports the failure or reads the error. A
 * handler named by reference (`.catch(report)`) is handed the error and passes.
 * Catches that do nothing at all are `emptyCatches`' and are not counted here.
 * The result is each one's line (1-based), to name them when a file gains one.
 */
export function swallowedCatchLines(source: ts.SourceFile, resolve: Resolve = () => undefined): number[] {
  const reporters = reporterNames(source, resolve);
  const lines: number[] = [];
  const line = (node: ts.Node) => source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
  const visit = (node: ts.Node): void => {
    if (
      ts.isCatchClause(node) &&
      !node.block.statements.every(isInert) &&
      !letsFailureOut(node.block, boundNames(node.variableDeclaration?.name), reporters)
    ) {
      lines.push(line(node));
    }
    const handler = rejectionHandler(node);
    if (handler && swallowsRejection(handler, reporters)) lines.push(line(handler));
    ts.forEachChild(node, visit);
  };
  visit(source);
  return lines;
}

export const swallowedCatches = (source: ts.SourceFile, resolve?: Resolve): number =>
  swallowedCatchLines(source, resolve).length;

/** The app's own modules, by `@/` path or relative path, parsed once each. */
export function appResolver(): Resolve {
  const parsed = new Map<string, ts.SourceFile>();
  return (specifier, from) => {
    const base = specifier.startsWith("@/")
      ? `${ROOT}/${specifier.slice(2)}`
      : specifier.startsWith(".")
        ? ts.sys.resolvePath(`${from.slice(0, from.lastIndexOf("/"))}/${specifier}`)
        : undefined;
    if (!base) return undefined;
    const file = [base, `${base}.ts`, `${base}.tsx`, `${base}/index.ts`, `${base}/index.tsx`]
      .find((candidate) => /\.tsx?$/.test(candidate) && ts.sys.fileExists(candidate));
    if (!file) return undefined;
    const source = parsed.get(file) ?? parseSource(file);
    parsed.set(file, source);
    return source;
  };
}

/** File -> count, for every production file `count` finds one in. */
export function catchCounts(count: (source: ts.SourceFile, resolve: Resolve) => number): Record<string, number> {
  const resolve = appResolver();
  const counts: Record<string, number> = {};
  for (const file of productionFiles()) {
    const found = count(parseSource(file), resolve);
    if (found > 0) counts[relative(file)] = found;
  }
  return counts;
}
