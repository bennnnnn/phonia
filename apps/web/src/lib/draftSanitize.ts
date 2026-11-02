/** Strip model form-slots (`[Your Name]`) from draft fences before render/copy. */

const FORM_SLOT_KEYS = [
  "name",
  "email",
  "address",
  "placeholder",
  "recipient",
  "manager",
  "boss",
  "subject",
  "company",
  "title",
  "date",
  "tbd",
];

function isDigitsOnly(s: string): boolean {
  if (!s) return false;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c < 48 || c > 57) return false;
  }
  return true;
}

function isWordChar(ch: string | undefined): boolean {
  if (!ch) return false;
  const c = ch.charCodeAt(0);
  return (c >= 97 && c <= 122) || (c >= 48 && c <= 57);
}

function containsWord(haystack: string, word: string): boolean {
  let from = 0;
  while (from <= haystack.length - word.length) {
    const idx = haystack.indexOf(word, from);
    if (idx < 0) return false;
    const before = idx === 0 ? undefined : haystack[idx - 1];
    const after = haystack[idx + word.length];
    if (!isWordChar(before) && !isWordChar(after)) return true;
    from = idx + 1;
  }
  return false;
}

function isFormSlot(inner: string): boolean {
  const s = inner.trim().toLowerCase();
  if (!s || s.length > 48) return false;
  if (isDigitsOnly(s)) return false;
  if (s.includes("http") || s.includes("(")) return false;
  for (const key of FORM_SLOT_KEYS) {
    if (containsWord(s, key)) return true;
  }
  return false;
}

function collapsePlaceholderGaps(text: string): string {
  const lines = text.split("\n");
  const cleaned: string[] = [];
  for (const line of lines) {
    let s = line;
    while (s.includes(" -  - ") || s.includes(" - - ")) {
      s = s.replace(" -  - ", " - ").replace(" - - ", " - ");
    }
    let compact = "";
    let space = false;
    for (let i = 0; i < s.length; i++) {
      const ch = s[i];
      if (ch === " " || ch === "\t") {
        if (!space) compact += " ";
        space = true;
      } else {
        compact += ch;
        space = false;
      }
    }
    cleaned.push(compact.trimEnd());
  }
  return cleaned.join("\n").trim();
}

export function stripDraftFormSlots(text: string): string {
  let out = "";
  let i = 0;
  while (i < text.length) {
    const open = text.indexOf("[", i);
    if (open < 0) {
      out += text.slice(i);
      break;
    }
    const close = text.indexOf("]", open + 1);
    if (close < 0) {
      out += text.slice(i);
      break;
    }
    const inner = text.slice(open + 1, close);
    if (isFormSlot(inner)) {
      out += text.slice(i, open);
      i = close + 1;
    } else {
      out += text.slice(i, close + 1);
      i = close + 1;
    }
  }
  return collapsePlaceholderGaps(out);
}
