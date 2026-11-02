/**
 * What a `\name` left for the native parser is: a function or operator name
 * set as a word (`\sin`, `\lim`), a symbol (`\varphi` is φ), a font that only
 * styles its argument, or unknown. An unknown name is never drawn — its
 * argument is — and is reported, so tests and telemetry can see what a reply
 * used that the renderer has no table entry for.
 */
import { createListenerSet } from "@/lib/listenerSet";
import { NAMED_FUNCTIONS } from "@/lib/math/latexCommands";
import { LATEX_OPERATOR_NAMES, LATEX_SYMBOLS } from "@/lib/math/latexSymbols.generated";
import { TEXT_STYLE_COMMANDS } from "@/lib/math/textMarkers";

type LatexNameKind = "function" | "operator" | "symbol" | "style" | "unknown";

/** amsmath's limit variants draw decorated "lim"; inline shows the word. */
const LIMIT_VARIANTS: Readonly<Record<string, string>> = {
  varliminf: "lim", varlimsup: "lim", varinjlim: "lim", varprojlim: "lim",
};

/** Symbols MathJax's maps do not hold as one character. */
const EXTRA_SYMBOLS: Readonly<Record<string, string>> = {
  textbackslash: "∖", hslash: "ℏ", degree: "°", celsius: "℃", ohm: "Ω", micro: "µ",
};

export function latexNameKind(name: string): LatexNameKind {
  if (NAMED_FUNCTIONS.has(name)) return "function";
  if (Object.hasOwn(LATEX_OPERATOR_NAMES, name) || Object.hasOwn(LIMIT_VARIANTS, name)) {
    return "operator";
  }
  if (Object.hasOwn(LATEX_SYMBOLS, name) || Object.hasOwn(EXTRA_SYMBOLS, name)) return "symbol";
  if (TEXT_STYLE_COMMANDS.has(name)) return "style";
  return "unknown";
}

/** The word an operator name is set as (`\liminf` is "lim inf"). */
export function operatorWord(name: string): string {
  return LATEX_OPERATOR_NAMES[name] ?? LIMIT_VARIANTS[name] ?? name;
}

/** The character a symbol name draws. */
export function symbolGlyph(name: string): string {
  return LATEX_SYMBOLS[name] ?? EXTRA_SYMBOLS[name] ?? "";
}

const unknownNames = createListenerSet<[name: string]>();

/** Hear every command name the native parser could not place. */
export const subscribeUnknownLatexCommands = unknownNames.subscribe;

export function reportUnknownLatexCommand(name: string): void {
  unknownNames.emit(name);
}
