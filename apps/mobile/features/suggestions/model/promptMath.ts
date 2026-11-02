/**
 * Turn a follow-up question into text MathText can typeset.
 * The model is asked for `$x^2 = 9$`. A bare `X^2 = 9` still gets dollars
 * so the caret is a superscript, matching the answer above the line.
 * Already-delimited spans are left alone.
 */

import { repairLeakedMath } from "@/lib/math/healMathSource";

const MATH_ISLAND =
  /[A-Za-z](?:\s*[\^_]\s*(?:\{[^{}\n]+\}|\d+))+(?:\s*[-+*/=]\s*(?:[A-Za-z]|\d+(?:\.\d+)?))*/g;

const GLUED_RADICAL = /\^\s*\d+\s*\\sqrt/;
const GLUED_VARIABLE = /(?<![A-Za-z\\^_{])[A-Za-z]\d+/;
const MIN_QUESTION_WORDS = 4;

function prevSignificant(text: string): string {
  const stripped = text.trimEnd();
  return stripped.length > 0 ? stripped[stripped.length - 1]! : "";
}

/** Spaces around = and a binary + or -. A power group is left as written. */
function spaceMathSpan(span: string): string {
  let out = "";
  let i = 0;
  while (i < span.length) {
    const ch = span[i]!;
    if (ch === "\\") {
      let j = i + 1;
      while (j < span.length && /[A-Za-z]/.test(span[j]!)) j += 1;
      out += span.slice(i, j);
      i = j;
      continue;
    }
    if (ch === "^" || ch === "_") {
      if (span[i + 1] === "{") {
        let depth = 0;
        let j = i + 1;
        while (j < span.length) {
          if (span[j] === "{") depth += 1;
          else if (span[j] === "}") {
            depth -= 1;
            if (depth === 0) {
              j += 1;
              break;
            }
          }
          j += 1;
        }
        out += span.slice(i, j);
        i = j;
        continue;
      }
      out += ch;
      i += 1;
      continue;
    }
    const prev = prevSignificant(out);
    const binary =
      ch === "=" ||
      ((ch === "+" || ch === "-") && prev !== "" && !"+=-*/(^".includes(prev));
    if (binary) {
      if (out.length > 0 && !out.endsWith(" ")) out += " ";
      out += `${ch} `;
      i += 1;
      while (span[i] === " ") i += 1;
      continue;
    }
    out += ch;
    i += 1;
  }
  return out.trim();
}

function mathStaysApart(text: string): boolean {
  let i = 0;
  while (i < text.length) {
    if (text[i] === "$") {
      const close = text.indexOf("$", i + 1);
      if (close > i + 1) {
        const span = text.slice(i + 1, close);
        if (GLUED_RADICAL.test(span) || GLUED_VARIABLE.test(span)) return false;
        i = close + 1;
        continue;
      }
    }
    i += 1;
  }
  return true;
}

function spaceDelimitedMath(text: string): string {
  let out = "";
  let i = 0;
  while (i < text.length) {
    if (text[i] === "$") {
      const close = text.indexOf("$", i + 1);
      if (close > i + 1) {
        out += `$${spaceMathSpan(text.slice(i + 1, close))}$`;
        i = close + 1;
        continue;
      }
    }
    out += text[i];
    i += 1;
  }
  return out;
}

/**
 * The line to send when a follow-up is tapped.
 * A fragment, or a number glued to a letter or a radical, is not a question.
 * A tight `$x=5$` is spaced so the letter and the number stay apart.
 */
export function suggestionToSend(text: string): string | null {
  const cleaned = text.replace(/\s+/g, " ").trim();
  // Letters in any script: a Russian or Amharic follow-up is a question too.
  const words = cleaned.match(/\p{L}{2,}/gu)?.length ?? 0;
  // A sum names its problem in few words ("What is 3 + 5?"), as the server allows.
  const longEnough = words >= MIN_QUESTION_WORDS || (/\d/.test(cleaned) && words >= 2);
  if (!cleaned.endsWith("?") || !longEnough) return null;
  if (!mathStaysApart(cleaned)) return null;
  return spaceDelimitedMath(repairDelimitedMath(cleaned));
}

function repairDelimitedMath(text: string): string {
  let out = "";
  let i = 0;
  while (i < text.length) {
    if (text[i] === "$") {
      const close = text.indexOf("$", i + 1);
      if (close > i + 1) {
        out += `$${repairLeakedMath(text.slice(i + 1, close))}$`;
        i = close + 1;
        continue;
      }
    }
    out += text[i];
    i += 1;
  }
  return out;
}

export function wrapSuggestionMath(text: string): string {
  let out = "";
  let i = 0;
  while (i < text.length) {
    if (text[i] === "$") {
      const close = text.indexOf("$", i + 1);
      if (close > i + 1) {
        out += text.slice(i, close + 1);
        i = close + 1;
        continue;
      }
    }
    MATH_ISLAND.lastIndex = i;
    const match = MATH_ISLAND.exec(text);
    if (!match) {
      out += text.slice(i);
      break;
    }
    const dollar = text.indexOf("$", i);
    if (dollar !== -1 && dollar < match.index) {
      out += text.slice(i, dollar);
      i = dollar;
      continue;
    }
    out += text.slice(i, match.index);
    out += `$${match[0]}$`;
    i = match.index + match[0].length;
  }
  return out;
}
