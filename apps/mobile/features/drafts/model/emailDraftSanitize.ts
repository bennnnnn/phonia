/** Keep draft text intact while rejecting unsafe placeholder recipient fields. */

type EmailDraftFields = {
  to?: string;
  subject?: string;
  body: string;
};

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

const LONELY_GREETINGS = ["Hi", "Hello", "Hey", "Dear"];

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

/** `[Your Name]` / `[Manager's Email Address]` — not `[1]` or markdown links. */
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

function looksLikeEmailAddress(value: string): boolean {
  const at = value.indexOf("@");
  if (at <= 0) return false;
  const dot = value.indexOf(".", at + 1);
  return dot > at + 1 && dot < value.length - 1 && !value.includes("[");
}

function hasFormSlot(value: string): boolean {
  let i = 0;
  while (i < value.length) {
    const open = value.indexOf("[", i);
    if (open < 0) return false;
    const close = value.indexOf("]", open + 1);
    if (close < 0) return false;
    if (isFormSlot(value.slice(open + 1, close))) return true;
    i = close + 1;
  }
  return false;
}

function isPlaceholderAddress(value: string): boolean {
  const v = value.trim();
  if (!v) return true;
  if (looksLikeEmailAddress(v) && !hasFormSlot(v)) return false;
  if (hasFormSlot(v)) return true;
  const lower = v.toLowerCase();
  if (lower.includes("email address") || lower.includes("placeholder")) return true;
  if (lower === "email" || lower === "recipient" || lower === "name") return true;
  return lower.endsWith("'s name") || lower.endsWith("'s email");
}

function tidyLonelyGreeting(body: string): string {
  const nl = body.indexOf("\n");
  const firstRaw = nl < 0 ? body : body.slice(0, nl);
  const rest = nl < 0 ? "" : body.slice(nl);
  let first = firstRaw.trim();
  while (first.endsWith(",") || first.endsWith(":")) {
    first = first.slice(0, -1).trim();
  }
  const lower = first.toLowerCase();
  for (const g of LONELY_GREETINGS) {
    if (lower === g.toLowerCase()) return `${g},${rest}`;
  }
  return body;
}

export function sanitizeEmailDraft(draft: EmailDraftFields): EmailDraftFields {
  const toRaw = draft.to?.trim() ?? "";
  const to = toRaw && !isPlaceholderAddress(toRaw) ? toRaw : undefined;
  // Body/subject placeholders may be intentional reusable-template slots.
  // Preserve them instead of manufacturing broken grammar such as "Hi," or
  // "Request for - This Friday". Only a placeholder recipient is unsafe to
  // hand to Gmail's To field, so that field still fails closed above.
  const subject = draft.subject?.trim() || undefined;
  const body = tidyLonelyGreeting(draft.body.trim());
  return {
    ...(to ? { to } : {}),
    ...(subject ? { subject } : {}),
    body,
  };
}
