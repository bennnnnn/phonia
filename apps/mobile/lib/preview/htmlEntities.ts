/**
 * Decode the character references in one HTML attribute value, as a browser's
 * tokenizer does before anything reads the value (HTML §13.2.5.72–80).
 *
 * `stripScripts` checks URL attributes for a script scheme. A browser reads
 * `href="&#106;avascript:…"` or `href="javascript&colon;…"` as
 * `javascript:…`, so the check has to see the decoded value, not the source.
 *
 * - Numeric references (`&#106;`, `&#x6A;`, `&#X6a`, any leading zeros, with or
 *   without the `;`) decode exactly as the spec says: digits are read greedily,
 *   0, surrogates and anything past U+10FFFF become U+FFFD, and 0x80–0x9F are
 *   the Windows-1252 characters.
 * - Named references: every name that decodes to ASCII (`&colon;`, `&Tab;`,
 *   `&NewLine;`, `&sol;`, …), and the legacy `&amp`, `&lt`, `&gt`, `&quot` a
 *   browser also reads without the `;` (not when `=` or a letter or digit
 *   follows, the attribute-value rule). Every other name decodes to a non-ASCII
 *   character, which can never be part of a URL scheme and is never removed by
 *   URL parsing, so it is left as written: decoding it could not change what a
 *   scheme check decides.
 */

/** HTML §13.2.5.80: a numeric reference to 0x80–0x9F names a Windows-1252 character. */
const WINDOWS_1252 =
  "€\u0081‚ƒ„…†‡ˆ‰Š‹Œ\u008DŽ\u008F" +
  "\u0090‘’“”•–—˜™š›œ\u009DžŸ";

/** Every named reference (with its `;`) whose characters are ASCII. */
const ASCII_NAMED = new Map<string, string>(
  Object.entries({
    "Tab;": "\t",
    "NewLine;": "\n",
    "excl;": "!",
    "quot;": '"',
    "QUOT;": '"',
    "num;": "#",
    "dollar;": "$",
    "percnt;": "%",
    "amp;": "&",
    "AMP;": "&",
    "apos;": "'",
    "lpar;": "(",
    "rpar;": ")",
    "ast;": "*",
    "midast;": "*",
    "plus;": "+",
    "comma;": ",",
    "period;": ".",
    "sol;": "/",
    "colon;": ":",
    "semi;": ";",
    "lt;": "<",
    "LT;": "<",
    "equals;": "=",
    "gt;": ">",
    "GT;": ">",
    "quest;": "?",
    "commat;": "@",
    "lsqb;": "[",
    "lbrack;": "[",
    "bsol;": "\\",
    "rsqb;": "]",
    "rbrack;": "]",
    "Hat;": "^",
    "lowbar;": "_",
    "UnderBar;": "_",
    "grave;": "`",
    "DiacriticalGrave;": "`",
    "lcub;": "{",
    "lbrace;": "{",
    "verbar;": "|",
    "vert;": "|",
    "VerticalLine;": "|",
    "rcub;": "}",
    "rbrace;": "}",
    "fjlig;": "fj",
  }),
);

/** The ASCII names a browser also reads without a `;`, longest first. */
const LEGACY_NAMES = ["quot", "QUOT", "amp", "AMP", "lt", "LT", "gt", "GT"] as const;

const NUMERIC_REFERENCE = /#(?:[xX]([0-9a-fA-F]+)|([0-9]+));?/y;
const NAMED_REFERENCE = /([A-Za-z0-9]+)(;?)/y;
const ALPHANUMERIC = /^[A-Za-z0-9]$/;

type Reference = { text: string; end: number };

function numericCharacter(code: number): string {
  if (code === 0 || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) return "�";
  if (code >= 0x80 && code <= 0x9f) return WINDOWS_1252.charAt(code - 0x80);
  return String.fromCodePoint(code);
}

function legacyReference(value: string, at: number, name: string): Reference | null {
  const legacy = LEGACY_NAMES.find((candidate) => name.startsWith(candidate));
  if (!legacy) return null;
  const end = at + legacy.length;
  const next = value.charAt(end);
  // In an attribute value, `&lt=` and `&ltx` stay literal.
  if (next === "=" || ALPHANUMERIC.test(next)) return null;
  return { text: ASCII_NAMED.get(`${legacy};`) ?? "", end };
}

/** The reference starting just after the `&` at `at - 1`, or null when the `&` is literal. */
function readReference(value: string, at: number): Reference | null {
  NUMERIC_REFERENCE.lastIndex = at;
  const numeric = NUMERIC_REFERENCE.exec(value);
  if (numeric) {
    const [, hex, decimal] = numeric;
    const code = hex !== undefined ? parseInt(hex, 16) : parseInt(decimal ?? "", 10);
    return { text: numericCharacter(code), end: NUMERIC_REFERENCE.lastIndex };
  }
  NAMED_REFERENCE.lastIndex = at;
  const named = NAMED_REFERENCE.exec(value);
  if (!named) return null;
  const [, name = "", semicolon] = named;
  const exact = semicolon ? ASCII_NAMED.get(`${name};`) : undefined;
  if (exact !== undefined) return { text: exact, end: NAMED_REFERENCE.lastIndex };
  return legacyReference(value, at, name);
}

export function decodeAttributeEntities(value: string): string {
  let out = "";
  let from = 0;
  for (let amp = value.indexOf("&"); amp >= 0; amp = value.indexOf("&", from)) {
    const reference = readReference(value, amp + 1);
    out += value.slice(from, amp) + (reference ? reference.text : "&");
    from = reference ? reference.end : amp + 1;
  }
  return out + value.slice(from);
}
