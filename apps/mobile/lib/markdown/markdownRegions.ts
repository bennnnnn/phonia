/**
 * Copy fenced regions byte for byte while rewriting the prose between them.
 * The API's twin is apps/api/app/modules/chat/markdown_regions.py; the
 * presentation passes on both sides walk a reply the same way.
 */

import { readInlineCodeSpan } from "@/lib/markdown/inlineCode";
import { closesFence, readFenceMarker, type OpenFence } from "@/lib/mdFenceScan";

/** Restaurant price tiers, ($) to ($$$$), are not maths. */
export const PRICE_TIER = /\(\s*\$+\s*\)/;

/**
 * Rewrite prose, and replace a closed fence when `rewriteFence` returns text.
 * `rewriteFence` receives the opener line, the body and the closer line; null
 * keeps that fence byte for byte. An unclosed fence stays raw.
 */
export function rewriteFenced(
  text: string,
  rewriteProse: (prose: string) => string,
  rewriteFence: (opener: string, body: string, closer: string) => string | null,
): string {
  if (!text) return rewriteProse(text);
  const out: string[] = [];
  let prose: string[] = [];
  let open: OpenFence | null = null;
  let opener = "";
  let body: string[] = [];
  const flush = () => {
    if (prose.length === 0) return;
    out.push(rewriteProse(prose.join("\n")));
    prose = [];
  };
  for (const line of text.split("\n")) {
    const marker = readFenceMarker(line);
    if (open) {
      if (marker && closesFence(marker, open)) {
        const replacement = rewriteFence(opener, body.join("\n"), line);
        if (replacement == null) out.push(opener, ...body, line);
        else out.push(replacement);
        open = null;
        body = [];
      } else {
        body.push(line);
      }
      continue;
    }
    // ` ``` | ```java` is a broken table cell, not a fence opener.
    if (marker && !marker.info.includes("|")) {
      flush();
      open = { char: marker.char, len: marker.len };
      opener = line;
      continue;
    }
    prose.push(line);
  }
  flush();
  if (open) out.push(opener, ...body);
  return out.join("\n");
}

/** Indented code and blockquotes keep their source spacing. */
export function leaveProseLine(line: string): boolean {
  if (line.startsWith("    ") || line.startsWith("\t")) return true;
  return line.trimStart().startsWith(">");
}

/**
 * Which lines belong to a display formula left open across lines. A `$$` or
 * `\[` that a line leaves open makes every line up to its closer one formula,
 * which the phone draws as one maths block: none of them is a prose line to
 * lay out. Inline code and price tiers hold no maths.
 */
export function displayMathLines(lines: string[]): boolean[] {
  const priceTiers = new RegExp(PRICE_TIER.source, "g");
  let closer: string | null = null;
  return lines.map((line) => {
    const after = displayCloser(line.replace(priceTiers, ""), closer);
    const kept = closer != null || after != null;
    closer = after;
    return kept;
  });
}

/** The display closer (`$$` or `\]`) still awaited after `line`. */
function displayCloser(line: string, open: string | null): string | null {
  let closer = open;
  let index = 0;
  // The backslashes just before `index`, counted as the scan passes them: an odd run
  // escapes the character there (`escapedAt` counted back from every index, which was
  // quadratic in a run of backslashes).
  let slashes = 0;
  while (index < line.length) {
    const codeEnd = closer == null ? readInlineCodeSpan(line, index) : null;
    if (codeEnd != null) {
      index = codeEnd;
      slashes = 0;
    } else if (slashes % 2 === 0 && line.startsWith("$$", index)) {
      if (closer == null || closer === "$$") closer = closer == null ? "$$" : null;
      index += 2;
      slashes = 0;
    } else if (slashes % 2 === 0 && line.startsWith("\\[", index) && closer == null) {
      closer = "\\]";
      index += 2;
      slashes = 0;
    } else if (slashes % 2 === 0 && line.startsWith("\\]", index) && closer === "\\]") {
      closer = null;
      index += 2;
      slashes = 0;
    } else {
      slashes = line[index] === "\\" ? slashes + 1 : 0;
      index += 1;
    }
  }
  return closer;
}
