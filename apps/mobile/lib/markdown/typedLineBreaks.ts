/**
 * A user's message keeps the line breaks they typed.
 *
 * The bubble renders Markdown, where a single newline is a soft break that joins two
 * lines with a space: "Budget range: $1,200\nPrimary use: coding" read as one line.
 * Each single newline in prose becomes a hard break. Blank lines (paragraphs) and fenced
 * code are left as they are.
 */
import { applyOutsideFences } from "@/lib/mdFenceScan";

const SOFT_BREAK = /([^\n])[ \t]*\n(?=[^\n])/g;

export function withTypedLineBreaks(text: string): string {
  return applyOutsideFences(text, (prose) => prose.replace(SOFT_BREAK, "$1  \n"));
}
