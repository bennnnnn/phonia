import { applyOutsideFences } from "@/lib/mdFenceScan";

// `1. **Read widely** – Consume diverse books…`: a bold title, a dash, then a sentence.
// A title that starts with a digit is a date or amount (`**1941** — Germany invades…`):
// a timeline reads along the line.
const TITLED_ITEM =
  /^(\s*(?:\d+[.)]|[-*+])\s+)(\*\*\p{L}[^*\n]*\*\*)\s+[–—-]\s+(\S.*)$/u;
// "**Price** – $5" or "**Speed** – fast" reads fine on one line.
const MIN_DESCRIPTION_WORDS = 5;

/**
 * A list item's bold title goes on its own line, its description underneath,
 * so a long list can be skimmed by title. A hard break keeps both in one
 * paragraph: the item stays tight, the title just stops sharing its line.
 */
export function breakListItemTitles(content: string): string {
  return applyOutsideFences(content, (prose) =>
    prose
      .split("\n")
      .map((line) => {
        const match = TITLED_ITEM.exec(line);
        if (
          !match ||
          match[3].trim().split(/\s+/).length < MIN_DESCRIPTION_WORDS
        )
          return line;
        const [, marker, title, description] = match;
        return `${marker}${title}\\\n${" ".repeat(marker.length)}${description}`;
      })
      .join("\n"),
  );
}
