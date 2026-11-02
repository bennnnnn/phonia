/**
 * Where ← and → put the caret in a math draft.
 *
 * A stop is a gap a reader can see: before and after a symbol, and inside each
 * box of a template. The gaps inside a template's own code are not stops:
 * between `\frac` and its `{`, or between two boxes (`}{`, `}^{`). So → goes
 * from the end of a numerator straight to the start of the denominator, and
 * from a template's last box to just after the template.
 *
 * Stops stay inside one `$…$` span. The gap after the closing `$` is prose, and
 * typing there would open a second span glued to the first (`$x$$+$`).
 */

type TokenKind = "command" | "open" | "close" | "atom";

const WHOLE_GROUP_COMMANDS = new Set(["mathbb", "mathrm", "text", "operatorname"]);
type Token = { start: number; end: number; kind: TokenKind; text: string };

function tokenize(text: string, from: number, to: number): Token[] {
  const out: Token[] = [];
  let i = from;
  const push = (end: number, kind: TokenKind) => {
    out.push({ start: i, end, kind, text: text.slice(i, end) });
    i = end;
  };
  while (i < to) {
    const ch = text[i]!;
    const next = text[i + 1];
    if (ch === "\\") {
      // Set braces are visible delimiters around a box.
      if (next === "{") {
        push(i + 2, "open");
        continue;
      }
      if (next === "}") {
        push(i + 2, "close");
        continue;
      }
      let j = i + 1;
      while (j < to && /[A-Za-z]/.test(text[j]!)) j += 1;
      // `\mathbb{R}`, `\mathrm{rad}`: one symbol, not a box to step into.
      if (WHOLE_GROUP_COMMANDS.has(text.slice(i + 1, j)) && text[j] === "{") {
        const close = text.indexOf("}", j);
        if (close !== -1 && close < to) {
          push(close + 1, "atom");
          continue;
        }
      }
      // `\,` and other one-character commands.
      if (j === i + 1) j = Math.min(i + 2, to);
      // `\pi ` keeps its space: one atom, not two.
      if (text[j] === " " && j < to) j += 1;
      push(j, "command");
      continue;
    }
    if ((ch === "^" || ch === "_") && next === "{") {
      push(i + 2, "open");
      continue;
    }
    if (ch === "{" || ch === "(" || ch === "[") {
      push(i + 1, "open");
      continue;
    }
    if (ch === "}" || ch === ")" || ch === "]") {
      push(i + 1, "close");
      continue;
    }
    push(i + 1, "atom");
  }
  return out;
}

/**
 * A gap inside a template's code: `\frac|{`, `\sin|(`, `}|{`, `}|^{`, `}|(`.
 * A symbol keeps its trailing space (`\pi `), so `π|(x)` stays a stop.
 */
function hiddenGap(left: Token, right: Token): boolean {
  if (right.kind !== "open") return false;
  if (left.kind === "command") return right.text !== "(" || !left.text.endsWith(" ");
  return left.kind === "close" && (left.text === "}" || left.text === "]");
}

/** The `$…$` span around `caret` (start just inside the opening `$`), or null. */
function mathSpanAt(text: string, caret: number): { start: number; end: number } | null {
  let open = -1;
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] !== "$") continue;
    if (open === -1) {
      open = i;
      continue;
    }
    if (caret > open && caret <= i) return { start: open + 1, end: i };
    open = -1;
  }
  if (open !== -1 && caret > open) return { start: open + 1, end: text.length };
  return null;
}

function caretStops(text: string, caret: number): number[] {
  const span = mathSpanAt(text, caret);
  if (!span) return [];
  const tokens = tokenize(text, span.start, span.end);
  const stops = [span.start];
  for (let k = 0; k < tokens.length; k += 1) {
    const left = tokens[k]!;
    const right = tokens[k + 1];
    if (right && hiddenGap(left, right)) continue;
    stops.push(left.end);
  }
  return stops;
}

function step(text: string, caret: number, dir: 1 | -1): number {
  const stops = caretStops(text, caret);
  if (stops.length === 0) {
    return Math.max(0, Math.min(text.length, caret + dir));
  }
  if (dir === 1) return stops.find((stop) => stop > caret) ?? caret;
  for (let k = stops.length - 1; k >= 0; k -= 1) {
    if (stops[k]! < caret) return stops[k]!;
  }
  return caret;
}

/** → : the next visible gap, entering and leaving template boxes in reading order. */
export function caretStepRight(text: string, caret: number): number {
  return step(text, caret, 1);
}

/** ← : the previous visible gap. */
export function caretStepLeft(text: string, caret: number): number {
  return step(text, caret, -1);
}
