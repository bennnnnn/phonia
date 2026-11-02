/**
 * Opening chunk for cloud TTS. Long enough to keep speaking while the rest
 * synthesizes; short enough that the first OpenRouter call is not the full reply.
 */

export const TTS_LEAD_MIN_CHARS = 120;
export const TTS_LEAD_MAX_CHARS = 160;
const SENTENCE_ENDS = new Set([".", "!", "?", "。", "！", "？", "።"]);

function isSentenceEnd(text: string, index: number): boolean {
  const ch = text[index] ?? "";
  if (!SENTENCE_ENDS.has(ch)) return false;
  if (ch === "。" || ch === "！" || ch === "？" || ch === "።") return true;
  return index + 1 >= text.length || text[index + 1] === " ";
}

export function splitTtsLead(plain: string): { lead: string; rest: string } {
  const normalized = plain.split(/\s+/).join(" ").trim();
  if (!normalized) return { lead: "", rest: "" };
  if (normalized.length <= TTS_LEAD_MIN_CHARS) {
    return { lead: normalized, rest: "" };
  }

  const window = normalized.slice(0, TTS_LEAD_MAX_CHARS);
  let cut = -1;
  for (let i = 0; i < window.length; i += 1) {
    if (!isSentenceEnd(window, i)) continue;
    cut = i + 1;
    if (cut >= TTS_LEAD_MIN_CHARS) break;
  }
  if (cut < TTS_LEAD_MIN_CHARS) {
    const space = window.lastIndexOf(" ");
    cut = space > 0 ? space : TTS_LEAD_MAX_CHARS;
  }

  const lead = normalized.slice(0, cut).trim();
  const rest = normalized.slice(cut).trim();
  if (!rest) return { lead: normalized, rest: "" };
  return { lead, rest };
}

/** Split a long reply into ~120–160 character clips so we never synthesize the whole page at once. */
export function splitTtsChunks(plain: string): string[] {
  const chunks: string[] = [];
  let remaining = plain.split(/\s+/).join(" ").trim();
  while (remaining) {
    const { lead, rest } = splitTtsLead(remaining);
    if (!lead) break;
    chunks.push(lead);
    remaining = rest;
  }
  return chunks;
}
