/**
 * Disarms `<meta http-equiv>` pragmas in untrusted HTML: the preview's Run tab
 * (lib/preview/previewSandbox.ts) and the browser export (lib/preview/htmlScriptStrip.ts).
 *
 * A pragma acts without any script. `refresh` sends the page elsewhere with no tap,
 * `set-cookie` writes a cookie, `content-security-policy` adds a policy,
 * `x-dns-prefetch-control: on` turns on DNS lookups that no CSP governs, `content-type`
 * declares a charset and `default-style` picks a stylesheet. A preview needs none of
 * them (its charset comes from how it is loaded), so every one goes; the only pragma a
 * preview keeps is the CSP the app writes itself (`keep`).
 *
 * Each tag is read the way the HTML tokenizer reads it: "/" separates attributes as
 * whitespace does, a quoted value may hold ">", and names match in any case. Character
 * references are never decoded in a name, so the value is never read: an encoded
 * `&#114;efresh` goes like any other.
 *
 * The attribute is renamed, not deleted. Deleting text lets the pieces either side of it
 * join into a new tag (`<scr<meta http-equiv=refresh>ipt>` became a live `<script>`);
 * renaming moves no tag boundary, so the rest of the document parses exactly as before
 * and one pass is final.
 */

const BLOCKED_PREFIX = "data-blocked-";
const PRAGMA_ATTRIBUTE = "http-equiv";

/** "<meta" opening a tag: the tag name ends at whitespace, "/" or ">". */
const META_TAG_OPEN = /<meta(?=[\t\n\f\r />]|$)/gi;

/**
 * Overlapping tags (a "<meta" inside another's value, or thousands left unclosed)
 * are each read in full, which hostile input could make quadratic. Past this many
 * characters read per character of input, the fallback below takes over.
 */
const READ_BUDGET_PER_CHAR = 4;

/**
 * The fallback: "http-equiv" wherever an attribute name can start (after whitespace,
 * "/" or a value's closing quote) and end. Every live pragma matches, in or out of a
 * `<meta>`, so it is as safe as reading tags, only less precise: prose that names the
 * attribute is renamed too.
 */
const ANY_PRAGMA_NAME = /(?<=[\t\n\f\r /"'])http-equiv(?=[\t\n\f\r />=]|$)/gi;

/** The tokenizer's whitespace (CR becomes LF before tokenizing). */
function isTagSpace(ch: string | undefined): boolean {
  return ch === " " || ch === "\t" || ch === "\n" || ch === "\f" || ch === "\r";
}

function isNameEnd(ch: string): boolean {
  return isTagSpace(ch) || ch === "/" || ch === ">" || ch === "=";
}

function skipTagSpace(html: string, at: number): number {
  let i = at;
  while (isTagSpace(html[i])) i++;
  return i;
}

/** Where the attribute value starting at `at` (past "=" and whitespace) ends. */
function valueEnd(html: string, at: number): number {
  const quote = html[at];
  if (quote === '"' || quote === "'") {
    const close = html.indexOf(quote, at + 1);
    return close === -1 ? html.length : close + 1;
  }
  let i = at;
  while (i < html.length && !isTagSpace(html[i]) && html[i] !== ">") i++;
  return i;
}

type MetaTag = { end: number; pragmaNames: number[] };

/**
 * Read the attributes of the tag whose name ends at `at`, up to its ">". A tag with
 * no ">" runs to the end of the text: whatever is appended later would close it.
 */
function readMetaTag(html: string, at: number): MetaTag {
  const pragmaNames: number[] = [];
  let i = at;
  while (i < html.length && html[i] !== ">") {
    if (isTagSpace(html[i]) || html[i] === "/") {
      i++;
      continue;
    }
    const start = i;
    i++; // a name keeps its first character, even "=" or a quote
    while (i < html.length && !isNameEnd(html[i])) i++;
    if (html.slice(start, i).toLowerCase() === PRAGMA_ATTRIBUTE) pragmaNames.push(start);
    const next = skipTagSpace(html, i);
    i = html[next] === "=" ? valueEnd(html, skipTagSpace(html, next + 1)) : next;
  }
  return { end: i, pragmaNames };
}

/**
 * Offsets of every http-equiv name on a `<meta>` tag, or null when reading them all
 * would cost more than the budget. Every "<meta" is read, even one inside a comment
 * or another tag's value: this reader cannot tell which are live, and renaming a dead
 * one is harmless.
 */
function pragmaNameOffsets(html: string, keep: string | undefined): number[] | null {
  let budget = READ_BUDGET_PER_CHAR * html.length;
  const offsets = new Set<number>();
  for (const open of html.matchAll(META_TAG_OPEN)) {
    if (keep !== undefined && html.startsWith(keep, open.index)) continue;
    const tag = readMetaTag(html, open.index + open[0].length);
    budget -= tag.end - open.index;
    if (budget < 0) return null;
    for (const at of tag.pragmaNames) offsets.add(at);
  }
  return [...offsets].sort((a, b) => a - b);
}

function renameAt(html: string, offsets: number[]): string {
  let out = "";
  let from = 0;
  for (const at of offsets) {
    out += html.slice(from, at) + BLOCKED_PREFIX;
    from = at;
  }
  return out + html.slice(from);
}

function renameEveryPragmaName(html: string): string {
  return html.replace(ANY_PRAGMA_NAME, `${BLOCKED_PREFIX}$&`);
}

/** Rename every http-equiv attribute on a `<meta>` tag, except in the tag that is exactly `keep`. */
export function disarmMetaPragmas(html: string, keep?: string): string {
  const offsets = pragmaNameOffsets(html, keep);
  if (offsets !== null) return renameAt(html, offsets);
  if (keep === undefined) return renameEveryPragmaName(html);
  return html.split(keep).map(renameEveryPragmaName).join(keep);
}
