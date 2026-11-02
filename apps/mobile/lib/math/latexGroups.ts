/** A `{...}` group. An escaped brace is content, not structure. */
export function readGroup(input: string, start: number): { value: string; next: number } | null {
  if (input[start] !== "{") return null;
  let depth = 0;
  for (let i = start; i < input.length; i += 1) {
    if (input[i] === "\\" && i + 1 < input.length) {
      i += 1;
      continue;
    }
    if (input[i] === "{") depth += 1;
    else if (input[i] === "}") {
      depth -= 1;
      if (depth === 0) {
        return { value: input.slice(start + 1, i), next: i + 1 };
      }
    }
  }
  return null;
}

/** SymPy emits y{\\left(x \\right)}; these braces group one function
 * argument and are invisible in TeX. Escaped set braces never enter here. */
export function isParenthesizedArgument(value: string): boolean {
  const text = value.trim();
  if (!text.startsWith("(") || !text.endsWith(")")) return false;
  let depth = 0;
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === "\\") {
      i += 1;
      continue;
    }
    if (text[i] === "(") depth += 1;
    if (text[i] === ")") depth -= 1;
    if (depth === 0 && i < text.length - 1) return false;
  }
  return depth === 0;
}

/** One TeX argument: a `{...}` group, a control word (`\pi`), or one character.
 * The braced form is returned as written; the others come back braced. */
function readArgument(input: string, start: number): { source: string; next: number } | null {
  let i = start;
  while (input[i] === " ") i += 1;
  const ch = input[i];
  if (ch === undefined || ch === "}") return null;
  if (ch === "{") {
    const group = readGroup(input, i);
    return group ? { source: input.slice(i, group.next), next: group.next } : null;
  }
  if (ch === "\\") {
    const word = /^\\[a-zA-Z]+/.exec(input.slice(i));
    const end = word ? i + word[0].length : i + 2;
    if (end > input.length) return null;
    return { source: `{${input.slice(i, end)}}`, next: end };
  }
  return { source: `{${ch}}`, next: i + 1 };
}

/** `\frac12` is TeX for one half: each argument may be a single token rather
 * than a `{...}` group, and KaTeX draws it. Brace those arguments so every
 * later reader only meets `\frac{1}{2}`; a model writing the short form
 * otherwise showed the letters "frac12". */
export function braceFractionArguments(input: string): string {
  let out = "";
  let i = 0;
  while (i < input.length) {
    const at = input.indexOf("\\frac", i);
    if (at < 0) break;
    const head = at + "\\frac".length;
    out += input.slice(i, head);
    i = head;
    // `\fraction` or another longer word is not a fraction.
    if (/[a-zA-Z]/.test(input[head] ?? "")) continue;
    const top = readArgument(input, head);
    const bottom = top ? readArgument(input, top.next) : null;
    if (!top || !bottom) continue;
    out += top.source + bottom.source;
    i = bottom.next;
  }
  return out + input.slice(i);
}

