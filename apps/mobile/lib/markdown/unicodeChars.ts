/**
 * Letters and digits as the API's presentation reads them (Python's
 * `str.isalpha` and `str.isalnum`): in every script, one whole character at a
 * time. Ethiopic, Arabic and Greek letters count, not only the ones with case.
 */

export const LETTER = /\p{L}/u;
export const ALNUM = /[\p{L}\p{N}]/u;

/** The character at `index`, whole even outside the BMP ("" past the end). */
export function charAt(text: string, index: number): string {
  const code = text.codePointAt(index);
  return code == null ? "" : String.fromCodePoint(code);
}

/** The last whole character of `text`. */
export function lastChar(text: string): string {
  return Array.from(text.slice(-2)).pop() ?? "";
}
