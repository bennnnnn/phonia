/**
 * A Python `>>>` transcript written as prose becomes a code block.
 *
 * Markdown reads `>>> two_sum([2, 7], 9)` as three nested quotes, so a reply
 * that shows a REPL session outside a fence draws stacked quote bars and runs
 * the call into its output. The transcript, up to the next blank line, is
 * wrapped in a ```python fence instead. The API does the same
 * (`apps/api/app/modules/chat/repl_transcript.py`), on the prose between
 * fences, so a transcript ends where a fence starts.
 */

import { applyOutsideFences } from "@/lib/mdFenceScan";

const PROMPT = /^[ \t]{0,3}>>>(?:[ \t]|$)/;

function fenceProse(prose: string): string {
  const lines = prose.split("\n");
  const out: string[] = [];
  let index = 0;
  while (index < lines.length) {
    if (!PROMPT.test(lines[index]!)) {
      out.push(lines[index]!);
      index += 1;
      continue;
    }
    const block: string[] = [];
    while (index < lines.length && lines[index]!.trim()) {
      block.push(lines[index]!.trim());
      index += 1;
    }
    out.push("```python", ...block, "```");
  }
  return out.join("\n");
}

export function fenceReplTranscripts(text: string): string {
  if (!text || !text.includes(">>>")) return text;
  return applyOutsideFences(text, fenceProse);
}
