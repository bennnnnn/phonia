/**
 * MathJax's TeX inventory, read from its own maps. Test support only: the
 * generated symbol tables and the native coverage test both start here.
 */
import { AllPackages } from "mathjax-full/js/input/tex/AllPackages.js";
import { AmsMethods } from "mathjax-full/js/input/tex/ams/AmsMethods.js";
import BaseMethods from "mathjax-full/js/input/tex/base/BaseMethods.js";
import { ConfigurationHandler } from "mathjax-full/js/input/tex/Configuration.js";
import { MapHandler } from "mathjax-full/js/input/tex/MapHandler.js";

import { styledLetters } from "@/lib/math/latexFonts";

type Entry = {
  char?: string;
  attributes?: { mathvariant?: string };
  func?: unknown;
  args?: unknown[];
};
type MapKind = "character" | "delimiter" | "macro" | "environment";

const NAMED = new Set([BaseMethods.NamedFn, BaseMethods.NamedOp, AmsMethods.NamedFn, AmsMethods.NamedOp]);

function mapNames(kind: MapKind): string[] {
  const names = new Set<string>();
  for (const pkg of AllPackages) {
    const handler = ConfigurationHandler.get(pkg)?.handler as Partial<Record<MapKind, string[]>> | undefined;
    for (const name of handler?.[kind] ?? []) names.add(name);
  }
  return [...names];
}

function mapOf(name: string): { kind: string; entries: [string, Entry][] } {
  const map = MapHandler.getMap(name) as unknown as { map?: Map<string, Entry> } | undefined;
  return { kind: map?.constructor.name ?? "", entries: map?.map ? [...map.map.entries()] : [] };
}

/** A control word's name: `\lmoustache` and `lmoustache` both read `lmoustache`. */
function controlWord(key: string): string | null {
  const name = key.startsWith("\\") ? key.slice(1) : key;
  return /^[A-Za-z]+$/.test(name) ? name : null;
}

function glyph(entry: Entry): string | null {
  const char = entry.char ?? "";
  if (!char) return null;
  // `\Bbbk` is the letter k drawn double-struck.
  if (entry.attributes?.mathvariant === "double-struck") return styledLetters(char, "double-struck");
  // A drawn backslash would read as source; the set-minus sign is what it means in maths.
  return char === "\\" ? "∖" : char;
}

export function mathJaxSymbolTables(): {
  symbols: Record<string, string>;
  operators: Record<string, string>;
} {
  const symbols: Record<string, string> = {};
  const operators: Record<string, string> = {};
  // Delimiters first: a character map's reading of the same name wins, so `\lt`
  // is "<" and not the angle bracket that `\left\lt` draws.
  const maps = [...mapNames("delimiter"), ...mapNames("macro")]
    .map(mapOf)
    .sort((a, b) => Number(a.kind !== "DelimiterMap") - Number(b.kind !== "DelimiterMap"));
  for (const { kind, entries } of maps) {
    for (const [key, entry] of entries) {
      const name = controlWord(key);
      if (!name) continue;
      if (kind === "CharacterMap" || kind === "DelimiterMap") {
        const char = glyph(entry);
        if (char) symbols[name] = char;
      } else if (NAMED.has(entry.func as never)) {
        const shown = typeof entry.args?.[0] === "string" ? entry.args[0] : name;
        operators[name] = shown.replace(/&thinsp;/g, " ");
      }
    }
  }
  // textcomp's text symbols insert one character each (`\textdegree` is °).
  for (const [key, entry] of mapOf("textcomp-macros").entries) {
    const name = controlWord(key);
    const char = entry.args?.[0];
    if (name && typeof char === "string" && [...char].length === 1 && !(name in symbols)) {
      symbols[name] = char === "\\" ? "∖" : char;
    }
  }
  return { symbols, operators };
}

/** Every control word MathJax defines, and every environment it knows. */
export function mathJaxCommands(): { commands: string[]; environments: string[] } {
  const commands = new Set<string>();
  for (const kind of ["delimiter", "macro", "character"] as const) {
    for (const name of mapNames(kind)) {
      for (const [key] of mapOf(name).entries) {
        const word = controlWord(key);
        if (word) commands.add(word);
      }
    }
  }
  const environments = new Set<string>();
  for (const name of mapNames("environment")) {
    for (const [key] of mapOf(name).entries) environments.add(key);
  }
  return { commands: [...commands].sort(), environments: [...environments].sort() };
}
