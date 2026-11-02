/** Linear markdown-fence scan — no nested regex on assistant text. */

import { parseFenceLang } from "@/lib/codeHighlight";

/**
 * CommonMark fence opener/closer: 3+ backticks or tildes, up to 3 leading spaces. A backtick
 * run's info holds no backtick: ```` ```inline``` ```` on one line is code, as on the server.
 */
export function readFenceMarker(
  line: string,
): { char: "`" | "~"; len: number; info: string } | null {
  let i = 0;
  while (i < line.length && i < 3 && line[i] === " ") i += 1;
  const char = line[i];
  if (char !== "`" && char !== "~") return null;
  let len = 0;
  while (i < line.length && line[i] === char) {
    len += 1;
    i += 1;
  }
  const info = line.slice(i).trim();
  if (len < 3 || (char === "`" && info.includes("`"))) return null;
  return { char, len, info };
}

/** Fence even when indented 4+ spaces (CommonMark would treat that as code). */
export function readFenceMarkerLoose(
  line: string,
): { char: "`" | "~"; len: number; info: string } | null {
  return readFenceMarker(line) ?? readFenceMarker(line.trimStart());
}

/** A fence left open: its marker's character and run length. */
export type OpenFence = { char: "`" | "~"; len: number };

/** A closer of `open`: its character, at least as long, nothing after it (CommonMark). */
export function closesFence(
  marker: { char: "`" | "~"; len: number; info: string },
  open: OpenFence,
): boolean {
  return marker.char === open.char && marker.len >= open.len && marker.info === "";
}

/**
 * The fence open after `line`, given the one open before it. A fence line inside an open
 * fence is its content unless it closes it; ` ``` | ```java` is a table cell's leftover,
 * not an opener. `loose` also reads a fence indented 4+ spaces, as in a list item.
 */
export function fenceAfterLine(
  open: OpenFence | null,
  line: string,
  loose = false,
): OpenFence | null {
  const marker = loose ? readFenceMarkerLoose(line) : readFenceMarker(line);
  if (open) return marker && closesFence(marker, open) ? null : open;
  return marker && !marker.info.includes("|") ? { char: marker.char, len: marker.len } : null;
}

/**
 * For each line of `text.split("\n")`, whether a fence holds it, its opener and closer
 * included. Line loops read this instead of flipping a flag on every ``` line, which a ```
 * shown inside a ~~~ block turned inside out (audit DUP-03). Loose by default, as the
 * loops it replaced: a fence indented in a list item is still one.
 */
export function fencedLines(text: string, loose = true): boolean[] {
  let open: OpenFence | null = null;
  return text.split("\n").map((line) => {
    const before = open;
    open = fenceAfterLine(open, line, loose);
    return before != null || open != null;
  });
}

/**
 * Apply `fn` only to prose between fenced regions. Fence openers, bodies, and
 * closers are copied byte-for-byte (including `$$` inside a Python string).
 */
export function applyOutsideFences(text: string, fn: (prose: string) => string): string {
  if (!text) return fn(text);
  const fenced = fencedLines(text, false);
  const out: string[] = [];
  let prose: string[] = [];

  const flushProse = () => {
    if (prose.length === 0) return;
    out.push(fn(prose.join("\n")));
    prose = [];
  };

  text.split("\n").forEach((line, index) => {
    if (!fenced[index]) {
      prose.push(line);
      return;
    }
    flushProse();
    out.push(line);
  });
  flushProse();
  return out.join("\n");
}

/** The text with the first closed ``lang`` fence's body replaced; null when there is none. */
export function replaceFirstClosedFenceBody(
  text: string,
  lang: string,
  newBody: string,
): string | null {
  const span = closedLangFences(text, lang)[0];
  if (span == null) return null;
  let stripped = newBody;
  while (stripped.endsWith("\n")) {
    stripped = stripped.slice(0, -1);
  }
  return text.slice(0, span.bodyStart) + `${stripped}\n` + text.slice(span.bodyEnd);
}

export function collectClosedFenceBodies(text: string, lang: string): string[] {
  const bodies: string[] = [];
  mapClosedLangFence(text, lang, (body) => {
    bodies.push(body);
    return `\`\`\`${lang}\n${body}\`\`\``;
  });
  return bodies;
}

/** Closed fences whose language (``parseFenceLang``) is ``lang``. */
function closedLangFences(text: string, lang: string): FenceSpan[] {
  const want = lang.toLowerCase();
  return scanFences(text).filter((span) => span.closed && parseFenceLang(span.info) === want);
}

/** Past a fence's closer line and its line break. */
function afterFence(text: string, span: FenceSpan): number {
  return text[span.end] === "\n" ? span.end + 1 : span.end;
}

/**
 * Rewrite each closed ``lang`` fence (opener through closer and its line break) as
 * ``replace(body)``, the body with its last line break. CommonMark rules, as ``scanFences``:
 * a ``` line inside a ~~~ block is that block's content (audit DUP-03).
 */
export function mapClosedLangFence(
  text: string,
  lang: string,
  replace: (body: string) => string,
): string {
  const pieces: string[] = [];
  let cursor = 0;
  for (const span of closedLangFences(text, lang)) {
    pieces.push(text.slice(cursor, span.start));
    pieces.push(replace(text.slice(span.bodyStart, span.bodyEnd)));
    cursor = afterFence(text, span);
  }
  pieces.push(text.slice(cursor));
  return pieces.join("");
}

export function stripClosedLangFence(text: string, lang: string): string {
  return mapClosedLangFence(text, lang, () => "");
}

/**
 * The text without the fences ``drop`` picks, in one scan. A closed fence goes with its
 * closer's line break; one left open (a reply streaming or cut mid-fence) is the last and
 * takes the rest of the text.
 */
export function dropFences(text: string, drop: (span: FenceSpan) => boolean): string {
  const pieces: string[] = [];
  let cursor = 0;
  for (const span of scanFences(text)) {
    if (!drop(span)) continue;
    pieces.push(text.slice(cursor, span.start));
    cursor = span.closed ? afterFence(text, span) : text.length;
  }
  pieces.push(text.slice(cursor));
  return pieces.join("");
}

/** The text without its ``lang`` fences: every closed one, and a last one left open. */
export function stripLangFence(text: string, lang: string): string {
  const want = lang.toLowerCase();
  // A fence names its language in the text: with no mention there is nothing to scan for.
  if (!text.toLowerCase().includes(want)) return text;
  return dropFences(text, (span) => parseFenceLang(span.info) === want);
}

/**
 * Walk closed fences with CommonMark closer rules (a ```math line is an
 * opener, never a closer). Unclosed openers are copied line-by-line so a
 * following tagged fence is not eaten.
 */
export function mapClosedFences(
  text: string,
  replace: (info: string, body: string, original: string) => string,
): string {
  if (!text) return text;
  const lines = text.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const marker = readFenceMarker(lines[i]!);
    if (!marker || marker.info.includes("|")) {
      out.push(lines[i]!);
      i += 1;
      continue;
    }
    let end = -1;
    for (let j = i + 1; j < lines.length; j += 1) {
      const inner = readFenceMarker(lines[j]!);
      if (inner && closesFence(inner, marker)) {
        end = j;
        break;
      }
    }
    if (end === -1) {
      out.push(lines[i]!);
      i += 1;
      continue;
    }
    const body = lines.slice(i + 1, end).join("\n");
    const original = lines.slice(i, end + 1).join("\n");
    out.push(replace(marker.info, body, original));
    i = end + 1;
  }
  return out.join("\n");
}

/** One fence and where it sits in the text. */
export type FenceSpan = {
  /** The opener's info string, e.g. `smiles` or `js title="x"`. */
  info: string;
  /** Everything between the opener and closer lines, without the final newline. */
  body: string;
  /** Offset of the opener line's first character. */
  start: number;
  /** Offset just past the closer line's last character (the end of the text if unclosed). */
  end: number;
  /** Offset of the first body line, and of the closer line (the end of the text if unclosed). */
  bodyStart: number;
  bodyEnd: number;
  closed: boolean;
};

/**
 * Every fence in reading order, by CommonMark rules: an opener is 3+ backticks or tildes, a
 * closer repeats the marker at least as long with no info string. An opener with no closer runs
 * to the end of the text, which is what a streaming reply looks like mid-fence. `loose` also
 * reads a fence indented 4+ spaces, as in a list item.
 */
export function scanFences(text: string, loose = false): FenceSpan[] {
  const read = loose ? readFenceMarkerLoose : readFenceMarker;
  const lines = text.split("\n");
  const starts: number[] = [];
  let offset = 0;
  for (const line of lines) {
    starts.push(offset);
    offset += line.length + 1;
  }
  const spans: FenceSpan[] = [];
  let i = 0;
  while (i < lines.length) {
    const marker = read(lines[i]!);
    if (!marker || marker.info.includes("|")) {
      i += 1;
      continue;
    }
    let close = -1;
    for (let j = i + 1; j < lines.length; j += 1) {
      const inner = read(lines[j]!);
      if (inner && closesFence(inner, marker)) {
        close = j;
        break;
      }
    }
    const last = close < 0 ? lines.length - 1 : close;
    const bodyStart = Math.min(text.length, starts[i]! + lines[i]!.length + 1);
    spans.push({
      info: marker.info,
      body: lines.slice(i + 1, close < 0 ? lines.length : close).join("\n"),
      start: starts[i]!,
      end: starts[last]! + lines[last]!.length,
      bodyStart,
      bodyEnd: close < 0 ? text.length : starts[close]!,
      closed: close >= 0,
    });
    i = last + 1;
  }
  return spans;
}

/** Closed fences whose opener is bare ``` (no language tag). */
export function mapUnlabeledClosedFences(
  text: string,
  replace: (body: string, original: string) => string,
): string {
  const pieces: string[] = [];
  let cursor = 0;
  for (const span of scanFences(text)) {
    if (!span.closed || span.info !== "") continue;
    const after = afterFence(text, span);
    pieces.push(text.slice(cursor, span.start));
    pieces.push(replace(text.slice(span.bodyStart, span.bodyEnd), text.slice(span.start, after)));
    cursor = after;
  }
  pieces.push(text.slice(cursor));
  return pieces.join("");
}
