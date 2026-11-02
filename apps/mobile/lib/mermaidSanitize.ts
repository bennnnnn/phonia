/** Quote mermaid node labels that contain raw parentheses.
 *
 * Unquoted `E[Grind Beans (Medium Grind)]` is invalid Mermaid and the
 * WebView parse-fails. A shape drawn inside the brackets keeps its marks
 * outside the quotes: the cylinder `DB[(Database)]` is left as it is, and
 * `DB[(Primary (rw))]` becomes `DB[("Primary (rw)")]`, not a box labelled
 * "(Primary (rw))". Linear scan — no nested regex. Twin of the server's
 * app/modules/chat/mermaid_sanitize.py.
 */

/** Marks of the shapes drawn inside `[...]`: cylinder, parallelograms, trapezoids. */
const SHAPE_EDGES: readonly (readonly [string, string])[] = [
  ["(", ")"],
  ["/", "/"],
  ["\\", "\\"],
  ["/", "\\"],
  ["\\", "/"],
];

/** `["…"]` is quoted already; `[[…]]` is a subroutine box. */
const BRACKETS: Record<string, readonly [string, string]> = { '"': ['["', '"]'], "[": ["[[", "]]"] };

function isQuoted(text: string): boolean {
  return text.length >= 2 && text.startsWith('"') && text.endsWith('"');
}

/** Every `)` closes an earlier `(` and none is left open. */
function parensBalanced(text: string): boolean {
  let depth = 0;
  for (const ch of text) {
    if (ch === "(") depth += 1;
    else if (ch === ")" && --depth < 0) return false;
  }
  return depth === 0;
}

/** The text between a node's brackets, with any parenthesised label quoted. */
function quoteMermaidLabel(body: string): string {
  const edge = SHAPE_EDGES.find(
    ([open, close]) =>
      body.length >= 2 &&
      body.startsWith(open) &&
      body.endsWith(close) &&
      // `[(a) and (b)]` is a box whose label opens and closes with brackets.
      (open !== "(" || parensBalanced(body.slice(1, -1))),
  );
  const [open, close] = edge ?? ["", ""];
  const label = body.slice(open.length, body.length - close.length);
  if ((!label.includes("(") && !label.includes(")")) || isQuoted(label)) return body;
  return `${open}"${label.replace(/"/g, "'")}"${close}`;
}

export function sanitizeMermaidNodeLabels(text: string): string {
  if (!text.includes("(") && !text.includes(")")) return text;
  const pieces: string[] = [];
  let index = 0;
  while (index < text.length) {
    const bracket = text.indexOf("[", index);
    if (bracket < 0) {
      pieces.push(text.slice(index));
      break;
    }
    pieces.push(text.slice(index, bracket));
    const [opener, closer] = BRACKETS[text[bracket + 1] ?? ""] ?? ["[", "]"];
    const close = text.indexOf(closer, bracket + opener.length);
    if (close < 0) {
      pieces.push(text.slice(bracket));
      break;
    }
    const body = text.slice(bracket + opener.length, close);
    pieces.push(opener === '["' ? text.slice(bracket, close + 2) : `${opener}${quoteMermaidLabel(body)}${closer}`);
    index = close + closer.length;
  }
  return pieces.join("");
}
