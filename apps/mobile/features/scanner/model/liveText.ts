const MATH_SIGNAL = /[0-9=+\-*/^<>≤≥√∫π%()]/;
const MATH_WORD = /\b(?:sin|cos|tan|log|ln|sqrt|lim|dx|dy|area|solve|find)\b/i;
/** NaCl, H2O, CO2. A lone capital pair such as OK is not a formula. */
const FORMULA_TOKEN =
  /\b(?:[A-Z][a-z]\d*|[A-Z]\d+)(?:[A-Z][a-z]?\d*)+\b|\b(?:[A-Z][a-z]?\d*)+(?:[A-Z][a-z]\d*|[A-Z]\d+)\b/;

export function normalizeLiveText(text: string): string {
  return text.replace(/\s+/g, " ").trim().toLowerCase();
}

/** Live framing is ready for math ink or a formula, even when the formula has no digit. */
export function hasUsefulScannerText(text: string): boolean {
  const trimmed = text.trim();
  if (trimmed.length < 2) return false;
  return (
    MATH_SIGNAL.test(trimmed) ||
    MATH_WORD.test(trimmed) ||
    /\d/.test(trimmed) ||
    FORMULA_TOKEN.test(trimmed)
  );
}
