/**
 * Where a streaming reply's chunk may end inside a list (`streamBlocks.ts`):
 * between two items of one top-level list, drawn as a list that goes on in
 * the next chunk, only when the cut cannot change how the list is drawn.
 */

/**
 * The top-level list the scan is in. A numbered list's `next` is the number
 * its next item shows (markdown numbers items from the first one, whatever
 * they say). `irregular`: a line markdown may read either way, or numbering
 * that does not run on, so no cut is made in this list. `content`: the column
 * the last item's content starts at; a line indented less is not inside it.
 * `wide`: a numbered list that reached 100, whose number column is wider than
 * any piece cut from it before drew.
 */
export type OpenList = {
  marker: string;
  next: number | null;
  irregular: boolean;
  content: number;
  wide: boolean;
};

/** What the chunk scan knows about the lines before the one it reads. */
type ListScan = { list: OpenList | null; inBlankRun: boolean };

/**
 * A numbered list's number column is as wide as its largest number. A chunk
 * that ends at item 10 or later already has the width every item up to 99
 * shares, so the items after it cannot widen the column the chunk drew.
 */
const MIN_NUMBERED_CUT = 11;
const MAX_NUMBERED_CUT = 99;
/** The first number with three digits: a list that shows it is `wide`. */
const WIDE_NUMBER = MAX_NUMBERED_CUT + 1;

/** An indented line: it belongs to the block above it. */
export const CONTINUATION_LINE_RE = /^(?: {2,}|\t)/;
const BULLET_ITEM_RE = /^([-*+])([ \t]+)/;
const NUMBERED_ITEM_RE = /^(\d{1,9})([.)])([ \t]+)/;
const THEMATIC_BREAK_RE = /^(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$/;

/** The column after `text`'s leading spaces and tabs, starting at `column` (tabs stop every 4). */
function columnAfterWhitespace(text: string, column = 0): number {
  for (const char of text) {
    if (char === " ") column += 1;
    else if (char === "\t") column += 4 - (column % 4);
    else break;
  }
  return column;
}

/**
 * Where an item's content starts: after its marker and the spaces after it.
 * Five or more spaces, or none before the end of the line, leave the content
 * one column after the marker (markdown's rule).
 */
function contentColumn(line: string, markerWidth: number, spaces: string): number {
  const after = columnAfterWhitespace(spaces, markerWidth);
  const empty = line.length === markerWidth + spaces.length;
  return empty || after - markerWidth >= 5 ? markerWidth + 1 : after;
}

/** The top-level list item `line` opens, if any: its marker, number and content column. */
function readListItem(
  line: string,
): { marker: string; number: number | null; content: number } | null {
  if (THEMATIC_BREAK_RE.test(line)) return null;
  const bullet = BULLET_ITEM_RE.exec(line);
  if (bullet) return { marker: bullet[1]!, number: null, content: contentColumn(line, 1, bullet[2]!) };
  const numbered = NUMBERED_ITEM_RE.exec(line);
  if (!numbered) return null;
  const markerWidth = numbered[1]!.length + 1;
  return {
    marker: numbered[2]!,
    number: Number(numbered[1]),
    content: contentColumn(line, markerWidth, numbered[3]!),
  };
}

/**
 * Follow the top-level list through a prose line; true when the line is the
 * next item of the open list and a cut before it draws the same list.
 */
export function listItemCut(state: ListScan, line: string): boolean {
  const item = readListItem(line);
  const list = state.list;
  if (item) {
    const sameList =
      list != null && list.marker === item.marker && (list.next === null) === (item.number === null);
    if (!sameList) {
      state.list = {
        marker: item.marker,
        next: item.number === null ? null : item.number + 1,
        irregular: false,
        content: item.content,
        wide: item.number !== null && item.number >= WIDE_NUMBER,
      };
      return false;
    }
    list.content = item.content;
    if (item.number === null) return !list.irregular;
    const shown = list.next ?? 0;
    list.next = shown + 1;
    if (shown >= WIDE_NUMBER) list.wide = true;
    if (item.number !== shown) {
      list.irregular = true;
      return false;
    }
    return !list.irregular && !list.wide && shown >= MIN_NUMBERED_CUT && shown <= MAX_NUMBERED_CUT;
  }
  if (CONTINUATION_LINE_RE.test(line)) {
    // Indented less than the item's content, a line is not inside the item:
    // `10. Step` then `   - detail` ends the numbered list in markdown.
    if (list && columnAfterWhitespace(line) < list.content) list.irregular = true;
    return false;
  }
  if (!list) return false;
  if (state.inBlankRun) {
    state.list = null;
  } else {
    // A lazy continuation, or a block that ends the list: either way, no cut.
    list.irregular = true;
  }
  return false;
}

/** The text at `at` opens the next item of `list`, as when the chunk before it was cut. */
export function listGoesOn(list: OpenList | null, prepared: string, at: number): boolean {
  if (!list) return false;
  const nl = prepared.indexOf("\n", at);
  const item = readListItem(prepared.slice(at, nl === -1 ? prepared.length : nl));
  if (!item || item.marker !== list.marker) return false;
  return list.next === null ? item.number === null : item.number === list.next;
}
