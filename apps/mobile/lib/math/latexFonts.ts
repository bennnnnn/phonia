/**
 * Letters in a maths alphabet (`\mathbb{E}` is 𝔼, `\mathfrak{g}` is 𝔤), from
 * Unicode's Mathematical Alphanumeric Symbols. Letters an older block already
 * holds (ℝ, ℭ) live there instead, so each alphabet lists its holes.
 */

type Alphabet = { upper: number; lower: number; digit?: number; holes: Record<string, string> };

const ALPHABETS: Record<"double-struck" | "fraktur", Alphabet> = {
  "double-struck": {
    upper: 0x1d538,
    lower: 0x1d552,
    digit: 0x1d7d8,
    holes: { C: "ℂ", H: "ℍ", N: "ℕ", P: "ℙ", Q: "ℚ", R: "ℝ", Z: "ℤ" },
  },
  fraktur: {
    upper: 0x1d504,
    lower: 0x1d51e,
    holes: { C: "ℭ", H: "ℌ", I: "ℑ", R: "ℜ", Z: "ℨ" },
  },
};

type LetterStyle = keyof typeof ALPHABETS;

/** Each ASCII letter (and, double-struck, digit) in `style`; anything else unchanged. */
export function styledLetters(text: string, style: LetterStyle): string {
  const alphabet = ALPHABETS[style];
  return Array.from(text, (ch) => {
    const hole = alphabet.holes[ch];
    if (hole) return hole;
    const code = ch.charCodeAt(0);
    if (ch >= "A" && ch <= "Z") return String.fromCodePoint(alphabet.upper + code - 65);
    if (ch >= "a" && ch <= "z") return String.fromCodePoint(alphabet.lower + code - 97);
    if (alphabet.digit != null && ch >= "0" && ch <= "9") {
      return String.fromCodePoint(alphabet.digit + code - 48);
    }
    return ch;
  }).join("");
}

/** The font commands whose letters change alphabet. Other fonts keep their letters. */
export const LETTER_STYLE_COMMANDS: Readonly<Record<string, LetterStyle>> = {
  mathbb: "double-struck",
  Bbb: "double-struck",
  symbb: "double-struck",
  mathbbm: "double-struck",
  mathfrak: "fraktur",
  symfrak: "fraktur",
  mathbffrak: "fraktur",
  symbffrak: "fraktur",
};
