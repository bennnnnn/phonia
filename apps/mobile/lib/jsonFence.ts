/**
 * A JSON card's fence arrives a few characters at a time while the reply
 * streams. Until its JSON parses, the card draws nothing rather than an error.
 *
 * A fence whose braces have all closed is finished even when it does not
 * parse (a raw newline in a string, a trailing comma): the card falls back to
 * readable text instead of waiting forever.
 */
export function isUnfinishedJson(content: string): boolean {
  try {
    JSON.parse(content);
    return false;
  } catch {
    return !closesItsBraces(content);
  }
}

/** Whether the text opens like JSON and its last brace or bracket closes the first. */
function closesItsBraces(content: string): boolean {
  const text = content.trim();
  if (!text.startsWith("{") && !text.startsWith("[")) return false;
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (const char of text) {
    if (inString) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') inString = false;
      continue;
    }
    if (char === '"') inString = true;
    else if (char === "{" || char === "[") depth += 1;
    else if (char === "}" || char === "]") depth -= 1;
  }
  return !inString && depth <= 0 && /[}\]]$/.test(text);
}

/** A JSON object: not null and not an array. What every fence reader expects at its root. */
export function isJsonRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** `text` parsed as JSON, as `{ value }`, or null when it is not JSON. */
export function readJson(text: string): { value: unknown } | null {
  try {
    return { value: JSON.parse(text) as unknown };
  } catch {
    return null;
  }
}

/** `text` parsed as JSON when it is an object, else null (bad JSON included). */
export function parseJsonRecord(text: string): Record<string, unknown> | null {
  const value = readJson(text)?.value;
  return isJsonRecord(value) ? value : null;
}
