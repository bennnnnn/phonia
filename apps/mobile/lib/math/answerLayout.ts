import { splitInlineMath } from "@/lib/markdown/inlineMath";

/** Break only independent equation alternatives; each separator stays with
 * its following branch and trailing parameter conditions remain untouched. */
export function splitAnswerBranches(text: string): string[] {
  if (/\\(?:begin|left|right)\b/.test(text)) return [text];
  const separators: { start: number; end: number }[] = [];
  const equations: number[] = [];
  let braces = 0;
  let parens = 0;
  let brackets = 0;
  for (let i = 0; i < text.length; i += 1) {
    if (braces === 0 && parens === 0 && brackets === 0) {
      const separator = text[i] === "\\"
        ? text.slice(i).match(/^\\text\{\s*or\s*\}/)?.[0]
        : text.startsWith("or", i) && /\s/.test(text[i - 1] ?? "") && /\s/.test(text[i + 2] ?? "")
          ? "or"
          : null;
      if (separator) {
        separators.push({ start: i, end: i + separator.length });
        i += separator.length - 1;
        continue;
      }
      if (text[i] === "=") equations.push(i);
    }
    if (text[i] === "\\" && /[\\{}()[\]]/.test(text[i + 1] ?? "")) {
      // Escaped structural delimiters are not safe line-break boundaries.
      return [text];
    }
    if (text[i] === "{") braces += 1;
    else if (text[i] === "}") braces -= 1;
    else if (text[i] === "(") parens += 1;
    else if (text[i] === ")") parens -= 1;
    else if (text[i] === "[") brackets += 1;
    else if (text[i] === "]") brackets -= 1;
    if (braces < 0 || parens < 0 || brackets < 0) return [text];
  }
  if (!separators.length || braces || parens || brackets) return [text];
  const starts = [0, ...separators.map((separator) => separator.end)];
  const ends = [...separators.map((separator) => separator.start), text.length];
  if (!starts.every((start, i) => equations.some((at) => at >= start && at < ends[i]))) return [text];
  const cuts = [0, ...separators.map((separator) => separator.start), text.length];
  return cuts.slice(0, -1).map((start, i) => text.slice(start, cuts[i + 1]).trim());
}

/**
 * An answer written as a sentence around its formulas ("$a = g\sin\theta$, which at
 * $30^\circ$ gives …"): two or more words outside the maths and no LaTeX there.
 * Its formulas keep their dollars, so the words are drawn as words.
 */
export function answerReadsAsProse(text: string): boolean {
  const parts = splitInlineMath(text);
  if (!parts.some((part) => part.type === "math")) return false;
  const prose = parts.filter((part) => part.type === "text").map((part) => part.value);
  if (prose.some((value) => /\\[A-Za-z]/.test(value))) return false;
  return prose.flatMap((value) => value.match(/[A-Za-z]{3,}/g) ?? []).length >= 2;
}
