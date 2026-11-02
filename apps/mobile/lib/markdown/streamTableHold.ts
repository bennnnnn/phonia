/**
 * A GFM table is a table only once its delimiter row (`|---|---|`) has
 * arrived. Before that, markdown-it reads the header line as a paragraph of
 * literal pipes, which then flips into a table: half a table shown raw. The
 * live tail holds a trailing header back until the line under it is complete.
 */

/**
 * A complete line that can be a table row: it opens and goes on with pipes.
 * The plain-text and PDF readers take a table's rows by the same test.
 */
export function looksLikePipeRow(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.startsWith("|") && trimmed.indexOf("|", 1) >= 0;
}

/**
 * `tail` without a trailing table header whose next line has not arrived yet.
 * Once the line under the header is complete the tail is shown as written:
 * a delimiter row makes it a table, any other line means it never was one.
 */
export function holdBackPendingTableHeader(tail: string): string {
  if (!tail.includes("|")) return tail;
  const lines = tail.split("\n");
  const partial = lines[lines.length - 1] ?? "";
  const lastComplete = lines.length - 2;
  // A line being typed that is not a table row: any table above it is finished.
  if (partial && !partial.trimStart().startsWith("|")) return tail;
  let runStart = lastComplete + 1;
  while (runStart > 0 && looksLikePipeRow(lines[runStart - 1] ?? "")) runStart -= 1;
  if (runStart > lastComplete && !partial) return tail;
  if (lastComplete + 1 - runStart >= 2) return tail;
  let offset = 0;
  for (let i = 0; i < runStart; i += 1) offset += (lines[i]?.length ?? 0) + 1;
  return tail.slice(0, offset);
}
