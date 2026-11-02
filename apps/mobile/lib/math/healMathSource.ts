/**
 * A dropped `\` turns `\frac{d^{2}}{dx^{2}}` into text the preview paints as
 * `frac{d ² }{dx ²}`. Restore the slash inside `$...$` so every key stays math.
 * Prose outside dollars is left alone (`sqrt{81}` in a sentence stays prose).
 */

const BRACED_COMMANDS = [
  "operatorname",
  "varepsilon",
  "epsilon",
  "partial",
  "infty",
  "nabla",
  "dfrac",
  "tfrac",
  "dbinom",
  "tbinom",
  "binom",
  "iiiint",
  "iiint",
  "oint",
  "iint",
  "sqrt",
  "mathrm",
  "mathbf",
  "mathit",
  "frac",
  "vec",
  "text",
  "cdot",
  "times",
  "arcsin",
  "arccos",
  "arctan",
  "sinh",
  "cosh",
  "tanh",
  "sum",
  "prod",
  "lim",
  "int",
  "sin",
  "cos",
  "tan",
  "cot",
  "sec",
  "csc",
  "log",
  "exp",
  "ln",
].sort((a, b) => b.length - a.length);

const AT_COMMAND = new RegExp(`^(${BRACED_COMMANDS.join("|")})(?=[{\\[^_])`);

/** `\f` from `\frac` is a form feed, so a decoder leaves `rac{…}{…}`. */
const EATEN_FRAC = /(?<![A-Za-z\\])\u000C?rac\{/g;

function eatenFracAt(text: string, i: number): boolean {
  if (!text.startsWith("rac{", i)) return false;
  const prev = text[i - 1];
  return prev !== "\\" && (prev == null || !/[A-Za-z]/.test(prev));
}

/**
 * The word "to" in "simplify to $…$" was copied into the formula as `t o` / `o t`.
 * Drop that word from the edges. A real `\to` keeps its backslash and stays.
 */
function stripLeakedTo(latex: string): string {
  if (!/\\[a-zA-Z]/.test(latex)) return latex;
  return latex.replace(/^\s*(?:t o|to|ot)\s+/, "").replace(/\s+(?:o t|to|ot)\s*$/, "");
}

/** Restore a fraction that lost `\f`, and drop a leaked "to" beside a real command. */
export function repairLeakedMath(latex: string): string {
  return stripLeakedTo(latex.replace(EATEN_FRAC, "\\frac{"));
}

function commandAt(text: string, i: number): string | null {
  const prev = text[i - 1];
  if (prev === "\\" || (prev != null && /[A-Za-z]/.test(prev))) return null;
  const match = AT_COMMAND.exec(text.slice(i));
  return match?.[1] ?? null;
}

/** Put a missing `\` back on a command inside inline math. Shifts carets that sit after the insertion. */
export function healDroppedCommandSlash(
  text: string,
  start = 0,
  end = start,
): { text: string; start: number; end: number } {
  let out = "";
  let math = false;
  let nextStart = start;
  let nextEnd = end;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]!;
    if (ch === "$" && text[i - 1] !== "\\") {
      math = !math;
      out += ch;
      continue;
    }
    if (math && eatenFracAt(text, i)) {
      out += "\\frac{";
      if (i < start) nextStart += 2;
      if (i < end) nextEnd += 2;
      i += 3;
      continue;
    }
    if (math) {
      const command = commandAt(text, i);
      if (command) {
        out += `\\${command}`;
        if (i < start) nextStart += 1;
        if (i < end) nextEnd += 1;
        i += command.length - 1;
        continue;
      }
    }
    out += ch;
  }
  return { text: out, start: nextStart, end: nextEnd };
}

export function hasBareCommand(text: string): boolean {
  return healDroppedCommandSlash(text).text !== text;
}

/** True when `next` is `prev` with exactly one `\` removed. */
export function droppedOnlySlash(prev: string, next: string): boolean {
  if (next.length !== prev.length - 1) return false;
  let skipped = false;
  let j = 0;
  for (let i = 0; i < prev.length; i += 1) {
    if (j < next.length && prev[i] === next[j]) {
      j += 1;
      continue;
    }
    if (skipped || prev[i] !== "\\") return false;
    skipped = true;
  }
  return skipped && j === next.length;
}
