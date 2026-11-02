/** Models sometimes use a bar as OR between alternative assignments.
 * Only complete branches for the same variable establish that meaning;
 * equals signs around an absolute value or set delimiter do not. */
const SEPARATOR_COMMANDS = [
  "\\bigm|", "\\Bigm|", "\\middle|", "\\Bigg|", "\\bigg|", "\\Big|", "\\big|", "\\mid", "\\vert",
];
const ASSIGNMENT = /^\s*([A-Za-z](?:_(?:[A-Za-z0-9]|\{[A-Za-z0-9]+\}))?)\s*=/;
const FIXED_DELIMITER = /\\(?:left|right|bigl|bigr|Bigl|Bigr|biggl|biggr|Biggl|Biggr)\s*$/;
const CLOSERS: Record<string, string> = { ")": "(", "]": "[", "}": "{" };

/** Check only lexical completeness, never simplify or reinterpret the value. */
function isCompleteValue(value: string): boolean {
  const text = value.trim();
  if (!text || text.includes("=") || /[,+\-*/^_]$/.test(text)) return false;
  const groups: string[] = [];
  let bars = 0;
  for (let i = 0; i < text.length; i += 1) {
    let ch = text[i];
    if (ch === "\\") {
      const command = /^\\[A-Za-z]+/.exec(text.slice(i));
      if (command) {
        if (["\\vert", "\\lvert", "\\rvert", "\\Vert", "\\lVert", "\\rVert", "\\mid"].includes(command[0])) bars += 1;
        i += command[0].length - 1;
        continue;
      }
      i += 1;
      ch = text[i];
      if (!ch) return false;
    }
    if ("([{".includes(ch)) groups.push(ch);
    else if (CLOSERS[ch]) {
      if (groups.pop() !== CLOSERS[ch]) return false;
    } else if (ch === "|") bars += 1;
  }
  return groups.length === 0 && bars % 2 === 0;
}

export function rewriteSolutionSeparatorBars(latex: string): string {
  const first = ASSIGNMENT.exec(latex);
  if (!first) return latex;
  const variable = first[1];
  const groups: string[] = [];
  const separators: { at: number; length: number }[] = [];
  for (let i = first[0].length; i < latex.length; i += 1) {
    let ch = latex[i];
    let separator = ch === "|" ? "|" : undefined;
    if (ch === "\\") {
      separator = SEPARATOR_COMMANDS.find((command) => latex.startsWith(command, i));
      if (separator && /[A-Za-z]/.test(separator.at(-1)!)) {
        if (/[A-Za-z]/.test(latex[i + separator.length] ?? "")) separator = undefined;
      }
      if (!separator) {
        const command = /^\\[A-Za-z]+/.exec(latex.slice(i));
        if (command) { i += command[0].length - 1; continue; }
        i += 1;
        ch = latex[i];
        if (!ch) return latex;
        // Escaped bars are literal norm/delimiter syntax, never OR candidates.
        if (ch === "|") continue;
      }
    }
    if (separator) {
      const fixed = FIXED_DELIMITER.test(latex.slice(Math.max(0, i - 16), i));
      if (groups.length === 0 && !fixed) {
        const next = ASSIGNMENT.exec(latex.slice(i + separator.length));
        if (next?.[1] === variable) separators.push({ at: i, length: separator.length });
      }
      i += separator.length - 1;
      continue;
    }
    if ("([{".includes(ch)) groups.push(ch);
    else if (CLOSERS[ch] && groups.pop() !== CLOSERS[ch]) return latex;
  }
  if (!separators.length || groups.length) return latex;
  const pieces: string[] = [];
  let start = 0;
  for (const separator of separators) {
    pieces.push(latex.slice(start, separator.at));
    start = separator.at + separator.length;
  }
  pieces.push(latex.slice(start));
  for (const piece of pieces) {
    const assignment = ASSIGNMENT.exec(piece);
    if (assignment?.[1] !== variable || !isCompleteValue(piece.slice(assignment[0].length))) return latex;
  }
  return pieces.join(" \\text{ or } ");
}

/** Turn `\\[ ... \\]` / `$$ ... $$` into `$...$` so user bubbles stay compact. */
export function displayMathToInline(text: string): string {
  let out = "";
  let i = 0;
  const n = text.length;
  while (i < n) {
    if (text.startsWith("$$", i)) {
      const close = text.indexOf("$$", i + 2);
      if (close < 0) {
        out += text.slice(i);
        break;
      }
      out += `$${text.slice(i + 2, close).trim()}$`;
      i = close + 2;
      continue;
    }
    if (text.startsWith("\\[", i)) {
      const close = text.indexOf("\\]", i + 2);
      if (close < 0) {
        out += text.slice(i);
        break;
      }
      out += `$${text.slice(i + 2, close).trim()}$`;
      i = close + 2;
      continue;
    }
    out += text[i];
    i += 1;
  }
  // Sent prose can contain a complete grouped slash fraction without dollar
  // delimiters: "Simplify (x^2-4)/(x^2-x-2)." The generic parenthetical
  // normalizer otherwise typesets each side separately and drops the grouping,
  // leaving the user's bubble as the ambiguous ``x²-4/x²-x-2``. Convert this
  // common complete form before markdown sees either pair of parentheses.
  return out.replace(
    /\(([^()\n]{1,160})\)\s*\/\s*\(([^()\n]{1,160})\)([.!?])?/g,
    (_full, numerator: string, denominator: string, punctuation?: string) =>
      `$\\frac{${numerator.trim()}}{${denominator.trim()}}${punctuation ?? ""}$`,
  );
}
