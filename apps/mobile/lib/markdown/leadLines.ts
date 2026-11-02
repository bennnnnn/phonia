/**
 * Lines that each open with a bold lead stay separate lines.
 *
 * A model lists options one per line with single breaks ("🇨🇭 **Switzerland — best for
 * quality of life** (…)", then "🇩🇪 **Germany — …**"), and Markdown joins single breaks
 * into one paragraph, so the options ran together. A run of two or more such lines
 * becomes one paragraph each. A lead may follow emoji or flags; list items, headings,
 * quotes, tables and indented lines are left alone (twin:
 * apps/api/app/modules/chat/lead_lines.py).
 */

import { rewriteFenced } from "@/lib/markdown/markdownRegions";

/** What may come before the bold lead: emoji, flags, their modifiers and joiners, spaces. */
const PREFIX = /^[\p{So}\p{Sk}\p{Mn}\p{Cf} ]*$/u;
const MAX_PREFIX = 16;

/** `**Lead**` (or `🇨🇭 **Lead**`) at the start of an unindented line. */
function opensWithBoldLead(line: string): boolean {
  const start = line.indexOf("**");
  if (start < 0 || line.startsWith(" ")) return false;
  // Counted in characters, as the API counts them (a flag is two, not four).
  const prefix = line.slice(0, start);
  if (Array.from(prefix).length > MAX_PREFIX || !PREFIX.test(prefix)) return false;
  return line.indexOf("**", start + 2) > start + 2;
}

function separate(prose: string): string {
  const lines = prose.split("\n");
  const out: string[] = [];
  lines.forEach((line, index) => {
    if (index > 0 && opensWithBoldLead(line) && opensWithBoldLead(lines[index - 1]!)) {
      out.push("");
    }
    out.push(line);
  });
  return out.join("\n");
}

/** Each line of a run of bold-lead lines becomes its own paragraph. */
export function separateLeadLines(text: string): string {
  return rewriteFenced(text, separate, () => null);
}
