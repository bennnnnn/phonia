/**
 * One owner of the chat thread (structure ticket ST-08): the list of messages on screen is
 * React state in `useChat`, and every change to it is a step of the turn reducer — the turn's
 * own frames, or a `thread_edit` another writer sends through `editThread`. Only `useChat`,
 * which holds the setter, and the reducer's command runner may touch the setter, and no other
 * file holds a list of messages in React state or a setter for one, so a second owner cannot
 * appear under a new name.
 *
 * Holders are read by type, not by spelling. A list of messages is an array whose element
 * takes any property from `Message` itself (`Message`, `Message & {…}`, `Pick`, `Partial`,
 * `Omit` of it, under any alias). A file holds one when:
 * - a React state hook (useState, useReducer, useSyncExternalStore, useOptimistic,
 *   useActionState, under any import name) answers a type that holds such a list anywhere
 *   (the state itself, a property, a Map's values);
 * - a hook that keeps generic React state (`useList<T>()`) is called with a type that makes
 *   its answer hold one;
 * - a name is typed as a setter of one: callable with one argument that takes the list or
 *   an updater of it, however its type is aliased and whatever optional parameters follow.
 * (useChat.test.tsx checks the hook hands out no setter under any key.)
 */
import * as ts from "typescript";

declare const __dirname: string;

const ROOT = ts.sys.resolvePath(`${__dirname}/../..`);
const OWNERS = ["features/chat/hooks/useChat.ts", "features/chat/model/chatTurnEffects.ts"];
/** The setter by its own name, whatever its type says. */
const SETTER_NAME = /\bsetMessages\b/;
/** React's hooks that keep state. */
const STATE_HOOKS = new Set(["useState", "useReducer", "useSyncExternalStore", "useOptimistic", "useActionState"]);
/** How deep a state's type is read for a list (a Map of chats of messages is three). */
const DEPTH = 4;
/** Reading the whole app's types takes seconds; more on a loaded machine. */
const PROGRAM_TIMEOUT_MS = 120_000;

function productionFiles(): string[] {
  return ["app", "components", "contexts", "features", "hooks", "lib", "ui"]
    .flatMap((dir) =>
      ts.sys.readDirectory(`${ROOT}/${dir}`, [".ts", ".tsx"], ["**/__tests__/**", "**/vendor/**"]),
    )
    .filter((file) => !file.endsWith(".d.ts"));
}

function compilerOptions(): ts.CompilerOptions {
  const parsed = ts.getParsedCommandLineOfConfigFile(`${ROOT}/tsconfig.json`, {}, {
    ...ts.sys,
    onUnRecoverableConfigFileDiagnostic: () => undefined,
  });
  return { ...parsed?.options, noEmit: true };
}

function parts(type: ts.Type): readonly ts.Type[] {
  return type.isUnion() || type.isIntersection() ? type.types : [type];
}

const fromLibrary = (node: ts.Node): boolean => node.getSourceFile().fileName.includes("/node_modules/");

/** Files of `files` holding a list of messages in React state, or a setter for one. */
function holdersByType(program: ts.Program, files: string[]): string[] {
  const checker = program.getTypeChecker();
  const types = program.getSourceFile(`${ROOT}/lib/api/types.ts`);
  const declaration = types?.statements.find(
    (node): node is ts.TypeAliasDeclaration => ts.isTypeAliasDeclaration(node) && node.name.text === "Message",
  );
  if (!declaration || !ts.isTypeLiteralNode(declaration.type)) {
    throw new Error("lib/api/types.ts no longer declares Message as an object type");
  }
  const members = new Set<ts.Node>(declaration.type.members);
  const vague = ts.TypeFlags.Any | ts.TypeFlags.Unknown | ts.TypeFlags.Never;

  /** A type with a property `Message` declares: Message, a narrower type, a Pick or Partial of it. */
  const fromMessage = (type: ts.Type): boolean =>
    !(type.flags & vague) &&
    checker.getPropertiesOfType(type).some((property) => property.declarations?.some((d) => members.has(d)));
  const isList = (type: ts.Type): boolean =>
    checker.isArrayType(type) && parts(checker.getTypeArguments(type as ts.TypeReference)[0]).some(fromMessage);

  /** `test` holds for `type` or for a type inside it: a member, an element, a property, a type argument. */
  const inside = (type: ts.Type, test: (part: ts.Type) => boolean, depth = 0, seen = new Set<ts.Type>()): boolean => {
    if (depth > DEPTH || seen.has(type)) return false;
    seen.add(type);
    return parts(type).some((part) => {
      if (test(part)) return true;
      if (part.flags & vague || !(part.flags & ts.TypeFlags.Object) || part.getCallSignatures().length > 0) {
        return false;
      }
      const reference = (part as ts.ObjectType).objectFlags & ts.ObjectFlags.Reference;
      if (reference && checker.getTypeArguments(part as ts.TypeReference).some((arg) => inside(arg, test, depth + 1, seen))) {
        return true;
      }
      // A library type's insides (a Date, a Promise, a React element) are not the app's state.
      if (part.getSymbol()?.declarations?.some(fromLibrary)) return false;
      return checker.getPropertiesOfType(part).some((property) =>
        inside(checker.getTypeOfSymbol(property), test, depth + 1, seen));
    });
  };
  const holdsList = (type: ts.Type): boolean => inside(type, isList);
  const holdsTypeParameter = (type: ts.Type): boolean =>
    inside(type, (part) => Boolean(part.flags & ts.TypeFlags.TypeParameter));

  /** A call of one of React's state hooks, under any import name. */
  const isStateHook = (call: ts.CallExpression): boolean => {
    const callee = ts.isPropertyAccessExpression(call.expression) ? call.expression.name : call.expression;
    let symbol = checker.getSymbolAtLocation(callee);
    if (symbol && symbol.flags & ts.SymbolFlags.Alias) symbol = checker.getAliasedSymbol(symbol);
    return Boolean(symbol && STATE_HOOKS.has(symbol.getName()) && symbol.declarations?.some(fromLibrary));
  };
  /** A function of the app that keeps React state of a type it is given (`useList<T>()`). */
  const keepsGenericState = new Map<ts.Node, boolean>();
  const wrapsGenericState = (target: ts.Declaration | undefined): boolean => {
    if (!target || !ts.isFunctionLike(target) || fromLibrary(target)) return false;
    const body = (target as ts.FunctionLikeDeclarationBase).body;
    if (!body) return false;
    const known = keepsGenericState.get(target);
    if (known !== undefined) return known;
    keepsGenericState.set(target, false);
    const found = (node: ts.Node): boolean =>
      (ts.isCallExpression(node) && (isStateHook(node) || wrapsGenericState(checker.getResolvedSignature(node)?.getDeclaration())) &&
        holdsTypeParameter(checker.getTypeAtLocation(node))) ||
      ts.forEachChild(node, found) === true;
    const result = found(body);
    keepsGenericState.set(target, result);
    return result;
  };
  const keepsList = (call: ts.CallExpression): boolean => {
    if (!holdsList(checker.getTypeAtLocation(call))) return false;
    return isStateHook(call) || wrapsGenericState(checker.getResolvedSignature(call)?.getDeclaration());
  };

  const optional = (parameter: ts.Symbol): boolean =>
    Boolean(parameter.declarations?.some((d) => ts.isParameter(d) && (d.questionToken || d.initializer || d.dotDotDotToken)));
  /** Callable with one argument that takes a list or an updater answering one: SetStateAction's shape. */
  const isSetter = (type: ts.Type): boolean =>
    type.getCallSignatures().some((signature) => {
      const [first, ...rest] = signature.parameters;
      if (!first || !rest.every(optional)) return false;
      const accepted = parts(checker.getTypeOfSymbol(first));
      return accepted.some((part) => part.getCallSignatures().length === 0 && holdsList(part)) &&
        accepted.some((part) => part.getCallSignatures().some((updater) => holdsList(updater.getReturnType())));
    });
  const isNamed = (node: ts.Node): node is ts.NamedDeclaration & { name: ts.Identifier } =>
    (ts.isParameter(node) || ts.isVariableDeclaration(node) || ts.isPropertySignature(node) ||
      ts.isPropertyDeclaration(node) || ts.isBindingElement(node)) && ts.isIdentifier(node.name);

  return files.filter((file) => {
    const source = program.getSourceFile(file);
    if (!source) throw new Error(`not in the program: ${file}`);
    const holds = (node: ts.Node): boolean =>
      (ts.isCallExpression(node) && keepsList(node)) ||
      (isNamed(node) && isSetter(checker.getTypeAtLocation(node.name))) ||
      ts.forEachChild(node, holds) === true;
    return holds(source);
  });
}

describe("the chat thread's owner", () => {
  it("only useChat and the turn's command runner hold the thread's state or setter", () => {
    const files = productionFiles();
    const program = ts.createProgram({ rootNames: files, options: compilerOptions() });
    const byName = files.filter((file) => SETTER_NAME.test(ts.sys.readFile(file) ?? ""));
    const holders = [...new Set([...byName, ...holdersByType(program, files)])]
      .map((file) => file.slice(ROOT.length + 1))
      .sort();
    expect(holders).toEqual(OWNERS);
  }, PROGRAM_TIMEOUT_MS);

  // 2026-11-01: the old check read spellings, and each of these held a thread past it.
  it("reads a holder by type, under any spelling", () => {
    const header = [
      'import * as React from "react";',
      "import {",
      "  useReducer, useRef, useState, useState as useLocal, useSyncExternalStore,",
      "  type Dispatch, type SetStateAction,",
      '} from "react";',
      'import type { Message } from "@/lib/api";',
      "type Thread = readonly Message[];",
    ].join("\n");
    const held = [
      "const [rows, setRows] = useState([] as Message[]);",
      "const [rows, setRows] = useState<Array<Message>>([]);",
      "const [rows, setRows] = useState<Thread>([]);",
      "const [rows, add] = useReducer((list: Message[], next: Message) => [...list, next], []);",
      "const [rows, setRows] = React.useState<(Message & { local?: boolean })[]>([]);",
      "const [rows, setRows] = useLocal<Message[]>([]);",
      "function useList<T>() { return useState<T[]>([]); }\nconst [rows, setRows] = useList<Message>();",
      "export function write(to: Dispatch<SetStateAction<Thread>>) { return to; }",
      "export type Props = { onRows: (next: SetStateAction<Message[]>) => void };",
      "const [box, setBox] = useState({ rows: [] as Message[] });",
      "const [state, send] = useReducer(\n  (s: { messages: Message[] }, m: Message) => ({ messages: [...s.messages, m] }),\n  { messages: [] },\n);",
      "function useList<T>() {\n  const [rows, setRows] = useState<T[]>([]);\n  return { rows, add: (row: T) => setRows((r) => [...r, row]) };\n}\nconst list = useList<Message>();",
      "export type Props = { onRows: (next: SetStateAction<Message[]>, why?: string) => void };",
      'const [rows, setRows] = useState<Pick<Message, "id" | "content">[]>([]);',
      "const [rows, setRows] = useState<Partial<Message>[]>([]);",
      'type Slim = Omit<Message, "model">;\nconst [rows, setRows] = useState<Slim[]>([]);',
      "declare const store: { subscribe: (cb: () => void) => () => void; read: () => Message[] };\nconst rows = useSyncExternalStore(store.subscribe, store.read);",
      "const [byChat, setByChat] = useState(new Map<string, Message[]>());",
    ];
    const kept = [
      "const [names, setNames] = useState<string[]>([]);",
      "const [count, setCount] = useState(0);",
      "const [rows, setRows] = useState<any[]>([]);",
      "const [ids, setIds] = useState<{ id: string; content: string }[]>([]);",
      "const [draft, setDraft] = useState<Message | null>(null);",
      "const rows = useRef<Message[]>([]);",
      'export const editThread = (update: SetStateAction<Message[]>, source: "image_turn") => [update, source];',
      "export const edit = (update: (rows: Message[]) => Message[]) => update;",
      "declare function split(rows: Message[]): [Message[], Message[]];\nconst [head, tail] = split([]);",
      "declare function useThreadView(): { messages: Message[]; edit: (u: SetStateAction<Message[]>, s: string) => void };\nconst view = useThreadView();",
      "function useList<T>() { return useState<T[]>([]); }\nconst names = useList<string>();",
    ];
    const probes = new Map(
      [...held, ...kept].map((body, index) => [`${ROOT}/features/probe${index}.tsx`, `${header}\n${body}\n`]),
    );
    const options = compilerOptions();
    const host = ts.createCompilerHost(options);
    const { fileExists, getSourceFile, readFile } = host;
    host.fileExists = (name) => probes.has(name) || fileExists.call(host, name);
    host.readFile = (name) => probes.get(name) ?? readFile.call(host, name);
    host.getSourceFile = (name, language, ...rest) => {
      const text = probes.get(name);
      return text === undefined
        ? getSourceFile.call(host, name, language, ...rest)
        : ts.createSourceFile(name, text, language, true);
    };
    const files = [...probes.keys()];
    const program = ts.createProgram({ rootNames: files, options, host });
    const holders = new Set(holdersByType(program, files));
    const wrong = [...probes].flatMap(([file, text], index) =>
      holders.has(file) === index < held.length ? [] : [`${index < held.length ? "missed" : "flagged"}: ${text.split("\n").slice(7).join(" ")}`]);
    expect(wrong).toEqual([]);
  }, PROGRAM_TIMEOUT_MS);
});
