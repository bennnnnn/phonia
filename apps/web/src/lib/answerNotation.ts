/** A header line of a server answer fence (after `verified: true`). Absent means the body is LaTeX. */

export const CHEMISTRY_ANSWER_NOTATION = "notation: chemistry";

const SUPERSCRIPT_DIGITS: Record<string, string> = {
  "-": "⁻",
  "0": "⁰",
  "1": "¹",
  "2": "²",
  "3": "³",
  "4": "⁴",
  "5": "⁵",
  "6": "⁶",
  "7": "⁷",
  "8": "⁸",
  "9": "⁹",
};

function superscript(exponent: string): string {
  return [...exponent].map((char) => SUPERSCRIPT_DIGITS[char] ?? char).join("");
}

/**
 * A typeset answer card as plain text. The web has no math renderer, and the server writes
 * physics cards as LaTeX with upright units: `3.97 \times 10^{-19}\,\mathrm{J}` reads
 * `3.97 × 10⁻¹⁹ J`, exactly the server's own plain answer. Anything else stays as written.
 */
export function readableLatexAnswer(latex: string): string {
  return latex
    .replace(/\\(?:mathrm|text)\{([^{}]*)\}/g, "$1")
    .replace(/_\{([^{}]*)\}/g, "_$1")
    .replace(/\\times 10\^\{(-?\d+)\}/g, (_match, exponent: string) => `× 10${superscript(exponent)}`)
    .replace(/\^\\circ/g, "°")
    .replace(/\\Omega(?![A-Za-z])/g, "Ω")
    .replace(/\\%/g, "%")
    .replace(/;\\quad /g, "; ")
    .replace(/\\quad(?![A-Za-z])/g, " ")
    .replace(/\\[,;:! ]/g, " ")
    .replace(/ {2,}/g, " ")
    .trim();
}

/** The server's mark on a card it checked; the phone draws it as a check, never as text. */
export const VERIFIED_ANSWER_MARKER = "verified: true";

export function visibleAnswerBody(raw: string): string {
  const lines = raw.replace(/\r\n/g, "\n").trim().split("\n");
  let chemistry = false;
  while (lines.length > 1) {
    const header = lines[0]!.trim();
    if (header === CHEMISTRY_ANSWER_NOTATION) chemistry = true;
    else if (header !== VERIFIED_ANSWER_MARKER) break;
    lines.shift();
  }
  const text = lines.join("\n").trim();
  if (chemistry) return text;
  return text.includes("\\") ? readableLatexAnswer(text) : text;
}
