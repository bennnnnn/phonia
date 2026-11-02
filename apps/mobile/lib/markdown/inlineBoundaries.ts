/**
 * Put a visible word space outside closed inline Markdown tokens.
 * The API's twin is apps/api/app/modules/chat/inline_boundaries.py;
 * docs/fixtures/presentation_cases.json holds both to the same output.
 * Fenced code, indented code, blockquotes, URLs, and math bodies stay intact.
 */

import { codeSpanOpensWithin, escapedAt } from "@/lib/markdown/inlineCode";
import { leaveProseLine, PRICE_TIER } from "@/lib/markdown/markdownRegions";
import { ALNUM, charAt, LETTER, lastChar } from "@/lib/markdown/unicodeChars";
import { applyOutsideFences } from "@/lib/mdFenceScan";

const OPEN_PUNCT = new Set("([{\"“‘«".split(""));
const CLOSE_PUNCT = new Set(".,;:!?)]}\"”’»…—–/%".split(""));

function isCjk(char: string): boolean {
  const code = char.codePointAt(0) ?? 0;
  return (
    (code >= 0x3040 && code <= 0x30ff) ||
    (code >= 0x3400 && code <= 0x9fff) ||
    (code >= 0xac00 && code <= 0xd7af) ||
    (code >= 0x0e00 && code <= 0x0e7f) ||
    (code >= 0xf900 && code <= 0xfaff) ||
    (code >= 0x20000 && code <= 0x3ffff)
  );
}

/** Letters and digits in scripts that separate words with spaces (Ethiopic and
 * Arabic as much as Latin), so not only the scripts with a letter case. */
function needsWordSpace(char: string): boolean {
  if (!char || /\s/.test(char) || isCjk(char)) return false;
  return ALNUM.test(char);
}


function glueBefore(previous: string): boolean {
  if (!previous || /\s/.test(previous) || OPEN_PUNCT.has(previous)) return false;
  return needsWordSpace(previous);
}

function glueAfter(next: string): boolean {
  if (!next || /\s/.test(next) || CLOSE_PUNCT.has(next)) return false;
  // A following delimiter is another inline token, not punctuation.
  if ("$*`[".includes(next)) return true;
  return needsWordSpace(next);
}

function skipCommand(text: string, index: number): number {
  let cursor = index + 1;
  if (cursor < text.length && /[A-Za-z]/.test(text[cursor])) {
    while (cursor < text.length && /[A-Za-z]/.test(text[cursor])) cursor += 1;
  } else if (cursor < text.length) {
    cursor += 1;
  }
  return cursor;
}

function readUrl(text: string, index: number): number | null {
  if (
    !text.startsWith("https://", index) &&
    !text.startsWith("http://", index) &&
    !text.startsWith("www.", index)
  ) {
    return null;
  }
  let cursor = index;
  while (cursor < text.length && !/\s/.test(text[cursor])) cursor += 1;
  return cursor;
}

function readCode(text: string, index: number): number | null {
  if (text[index] !== "`") return null;
  let length = 0;
  while (index + length < text.length && text[index + length] === "`") length += 1;
  const close = text.indexOf("`".repeat(length), index + length);
  if (close < 0 || close === index + length || text.slice(index + length, close).includes("\n")) {
    return null;
  }
  return close + length;
}

const PRICE_TIER_AT = new RegExp(PRICE_TIER.source, "y");

function readPriceTier(text: string, index: number): number | null {
  PRICE_TIER_AT.lastIndex = index;
  return PRICE_TIER_AT.test(text) ? PRICE_TIER_AT.lastIndex : null;
}

/** `$2$` (or `$2.$`): one number. Not "$5 and $10" (two prices) or "$5$10". */
function bareNumber(body: string, next: string | undefined): boolean {
  return /^\s*\d[\d,]*(?:\.\d*)?\s*$/.test(body) && !/\d/.test(next ?? "");
}

/**
 * End of the `$...$` span opening at `index`. A pair never reaches across an
 * inline code span (markdown-it reads the code first), and a bare number
 * (`$2$`) is a span: when it was skipped as a price, its closer opened a new
 * span with the next dollar on the line and padded `$2 $`.
 */
function readMath(text: string, index: number): number | null {
  if (escapedAt(text, index)) return null;
  if (text.startsWith("$$", index)) {
    const close = text.indexOf("$$", index + 2);
    if (close < 0 || close === index + 2 || text.slice(index + 2, close).includes("\n")) return null;
    if (codeSpanOpensWithin(text, index + 2, close)) return null;
    return close + 2;
  }
  if (text[index] !== "$" || (index > 0 && text[index - 1] === "$")) return null;
  let from = index + 1;
  while (from < text.length) {
    const close = text.indexOf("$", from);
    if (close < 0 || text.slice(index + 1, close).includes("\n")) return null;
    if (escapedAt(text, close)) {
      from = close + 1;
      continue;
    }
    if (close + 1 < text.length && text[close + 1] === "$") return null;
    if (codeSpanOpensWithin(text, index + 1, close)) return null;
    const body = text.slice(index + 1, close);
    if (!body.trim()) return null;
    // A price, then a dollar before a digit: two prices. Padding
    // "$38.40 = $19.20" as maths saved "$ 19.20", which then read as maths.
    // Maths glued to a digit (`$a_n$2`) is still padded.
    if (/\d/.test(text[close + 1] ?? "") && /^\s*\d/.test(body)) return null;
    if (/^\d/.test(body) && !/[\\=^_]/.test(body) && !bareNumber(body, text[close + 1])) {
      return null;
    }
    return close + 1;
  }
  return null;
}

function readLink(text: string, index: number): number | null {
  let cursor = index;
  if (text[cursor] === "!" && text[cursor + 1] === "[") cursor += 1;
  if (text[cursor] !== "[") return null;
  const close = text.indexOf("]", cursor + 1);
  if (close < 0 || text.slice(cursor + 1, close).includes("\n")) return null;
  if (text[close + 1] === "(") {
    const end = text.indexOf(")", close + 2);
    if (end < 0 || text.slice(close + 2, end).includes("\n")) return null;
    return end + 1;
  }
  if (text[close + 1] === "[") {
    const end = text.indexOf("]", close + 2);
    if (end < 0 || text.slice(close + 2, end).includes("\n")) return null;
    return end + 1;
  }
  return null;
}

function readBold(text: string, index: number): number | null {
  if (!text.startsWith("**", index)) return null;
  const markerLen = text.startsWith("***", index) ? 3 : 2;
  const close = text.indexOf("*".repeat(markerLen), index + markerLen);
  if (close < 0) return null;
  const inner = text.slice(index + markerLen, close);
  if (!inner.trim() || inner.includes("\n")) return null;
  return close + markerLen;
}

function readEmphasis(text: string, index: number): number | null {
  if (text[index] !== "*" || text.startsWith("**", index)) return null;
  if (text[index + 1] === " ") return null;
  const close = text.indexOf("*", index + 1);
  if (close < 0 || text.startsWith("**", close)) return null;
  const inner = text.slice(index + 1, close);
  if (!inner || inner.includes("\n")) return null;
  if (![...inner].some((char) => LETTER.test(char) && !isCjk(char))) return null;
  return close + 1;
}

// One letter in bold or italics, inside a word: a mnemonic's "**A**ffect is
// **A**ction" became "**A** ffect is **A** ction" (2026-10-29). Letters of an alphabet
// (Latin, Greek, Cyrillic): in a syllabary such as Amharic's, one sign is a syllable. A
// longer span ("the**US**economy"), or one against a digit ("**at**40"), is still a missing space. The
// server's twin is apps/api/app/modules/chat/inline_boundaries.py.
const ALPHABET = "A-Za-z\u00c0-\u024f\u0370-\u03ff\u0400-\u04ff";
const IN_WORD = new RegExp(`^(\\*{1,3})[${ALPHABET}]\\1$`);
const ALPHABET_LETTER = new RegExp(`^[${ALPHABET}]$`);

function inWord(span: string, neighbour: string): boolean {
  return ALPHABET_LETTER.test(neighbour) && IN_WORD.test(span);
}

function emit(out: string[], span: string, next: string): void {
  const previous = out.length > 0 ? lastChar(out[out.length - 1]) : "";
  if (out.length > 0 && glueBefore(previous) && !inWord(span, previous)) out.push(" ");
  out.push(span);
  const after = charAt(next, 0);
  if (glueAfter(after) && !inWord(span, after)) out.push(" ");
}

function repairLine(line: string): string {
  const out: string[] = [];
  let index = 0;
  while (index < line.length) {
    if (line[index] === "\\") {
      const end = skipCommand(line, index);
      out.push(line.slice(index, end));
      index = end;
      continue;
    }
    // A URL or a ($$) price tier is copied as written.
    const verbatimEnd = readUrl(line, index) ?? readPriceTier(line, index);
    if (verbatimEnd != null) {
      out.push(line.slice(index, verbatimEnd));
      index = verbatimEnd;
      continue;
    }
    const readers = [readCode, readMath, readLink, readBold, readEmphasis];
    let matched = false;
    for (const reader of readers) {
      const end = reader(line, index);
      if (end == null) continue;
      emit(out, line.slice(index, end), line.slice(end, end + 2));
      index = end;
      matched = true;
      break;
    }
    if (matched) continue;
    if (line[index] === "*") {
      let cursor = index;
      while (cursor < line.length && line[cursor] === "*") cursor += 1;
      if (cursor - index >= 3 || cursor === line.length || /\s/.test(line[cursor] ?? "")) {
        out.push(line.slice(index, cursor));
        index = cursor;
        continue;
      }
    }
    const char = charAt(line, index);
    out.push(char);
    index += char.length;
  }
  return out.join("");
}

function repairProse(prose: string): string {
  return prose
    .split("\n")
    .map((line) => (leaveProseLine(line) ? line : repairLine(line)))
    .join("\n");
}

export function repairInlineTokenBoundaries(text: string): string {
  return applyOutsideFences(text, repairProse);
}
