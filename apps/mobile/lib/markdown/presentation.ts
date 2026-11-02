/**
 * Assistant Markdown presentation, the contract the API applies before a
 * reply is saved (apps/api/app/modules/chat/presentation.py).
 * REPL transcripts become code, then boundaries, then one reasoning state per
 * calculation row. docs/fixtures/presentation_cases.json holds both sides to
 * the same output.
 *
 * The phone presents only what the server has not: the text still streaming,
 * and rows saved before SERVER_PRESENTATION_CUTOVER.
 */

import { layoutCalculations } from "@/lib/markdown/calculationLayout";
import { repairInlineTokenBoundaries } from "@/lib/markdown/inlineBoundaries";
import { readInlineCodeSpan } from "@/lib/markdown/inlineCode";
import { readInlineMathSpan } from "@/lib/markdown/inlineMath";
import { separateLeadLines } from "@/lib/markdown/leadLines";
import { codeNotation } from "@/lib/markdown/notationSpans";
import { fenceReplTranscripts } from "@/lib/markdown/replTranscript";
import { holdBackPendingTableHeader } from "@/lib/markdown/streamTableHold";
import { normalizeImplicitMath } from "@/lib/math/normalizeImplicit";
import { currencyDollarAt } from "@/lib/math/proseDollars";
import { unfinishedFormulaAt } from "@/lib/math/streaming";
import { isServerMessageId } from "@/lib/serverMessageId";

/**
 * Assistant rows saved from this instant on were presented by the API with
 * the contract the corpus holds, so the phone shows them as saved.
 *
 * The finalize path first presented a saved reply in #1525 (07f46a28,
 * 2026-09-28). The contract changed on both sides after that: currency
 * dollars (d3df9cc0, 2026-10-04), REPL transcripts (9d125106, 2026-10-14),
 * inline code beside maths (9d95f5bd / 3e4aa89b, 2026-10-15), and ES-06
 * (2026-10-16: display formulas, price tiers, letters in every script,
 * live-talk rows). API deploys are manual and not in git, so the cut-over is
 * a month after the last change. Older rows are presented here, as before. A
 * rule change that must reach rows the server saved moves this date.
 */
export const SERVER_PRESENTATION_CUTOVER = Date.parse("2026-11-16T00:00:00Z");

/** True for a saved row (a server id, not `streaming` or `streamed-…`) that
 * the server presented before saving it. */
export function isServerPresentedRow(row: {
  id: string;
  created_at: string;
}): boolean {
  if (!isServerMessageId(row.id)) return false;
  const created = Date.parse(row.created_at);
  return Number.isFinite(created) && created >= SERVER_PRESENTATION_CUTOVER;
}

export function presentAssistantMarkdown(text: string): string {
  if (!text) return text;
  return layoutCalculations(
    repairInlineTokenBoundaries(separateLeadLines(codeNotation(fenceReplTranscripts(text)))),
  );
}

/** Index of an unclosed `$`, `$$`, `\(`, or `\[`, or null when every opener closed.
 * A dollar inside inline code is code, and an open `$` cannot close past a
 * code span, so it is a lone dollar. */
function openMathStart(prose: string): number | null {
  let inline = false;
  let display = false;
  let paren = false;
  let bracket = false;
  let openAt = -1;
  let i = 0;
  while (i < prose.length) {
    if (prose[i] === "`" && !display && !paren && !bracket) {
      const codeEnd = readInlineCodeSpan(prose, i);
      if (codeEnd != null) {
        inline = false;
        openAt = -1;
        i = codeEnd;
        continue;
      }
    }
    if (prose.startsWith("$$", i)) {
      if (display) {
        display = false;
        openAt = -1;
      } else if (!inline && !paren && !bracket) {
        display = true;
        openAt = i;
      }
      i += 2;
      continue;
    }
    const pair = prose.startsWith("\\(", i)
      ? "paren"
      : prose.startsWith("\\)", i)
        ? "paren-close"
        : prose.startsWith("\\[", i)
          ? "bracket"
          : prose.startsWith("\\]", i)
            ? "bracket-close"
            : null;
    if (pair === "paren" && !inline && !display && !paren && !bracket) {
      paren = true;
      openAt = i;
      i += 2;
      continue;
    }
    if (pair === "paren-close" && paren) {
      paren = false;
      openAt = -1;
      i += 2;
      continue;
    }
    if (pair === "bracket" && !inline && !display && !paren && !bracket) {
      bracket = true;
      openAt = i;
      i += 2;
      continue;
    }
    if (pair === "bracket-close" && bracket) {
      bracket = false;
      openAt = -1;
      i += 2;
      continue;
    }
    if (prose[i] === "$" && !display && !paren && !bracket) {
      if (inline) {
        inline = false;
        openAt = -1;
      } else {
        // A formula the renderer reads is whole, and a price it pairs with
        // nothing opens nothing: "It costs $5, and $4! = 24$." holds no open
        // dollar. An unclosed formula after a price still waits.
        const span = readInlineMathSpan(prose, i);
        if (span) {
          i = span.end;
          continue;
        }
        if (!currencyDollarAt(prose, i) || unfinishedFormulaAt(prose, i)) {
          inline = true;
          openAt = i;
        }
      }
    }
    i += 1;
  }
  return inline || display || paren || bracket ? openAt : null;
}

/** Same island wrap the settled preprocess uses, outside fences and finished
 * `\(...\)` / `\[...\]` / `$$` spans. Wrapping a line that is already inside
 * those delimiters inserts a second `$` and clips the formula. An opener
 * that has not closed yet stays raw so a later token can finish it. */
function presentStreamProse(prose: string, presented: boolean): string {
  if (!prose) return prose;
  const openAt = openMathStart(prose);
  const head = openAt == null ? prose : prose.slice(0, openAt);
  const open = openAt == null ? "" : prose.slice(openAt);
  const present = presented ? layoutCalculations : presentAssistantMarkdown;
  // Notation becomes code before the maths wrap can read "(=O)" as maths.
  const wrapped = head
    ? present(normalizeImplicitMath(codeNotation(head)))
    : "";
  return wrapped + open;
}

/**
 * Repair a streaming tail without scanning an open fence body, and hold back a
 * table header still waiting for its delimiter row. `presented`
 * text is the server's saved reply, still in stream layout while its row
 * settles: as in the settled preprocess, its prose stays as saved and only the
 * maths rows the wrap builds are laid out, so settling does not move it.
 */
export function presentStreamTail(tail: string, presented = false): string {
  if (!tail) return tail;
  const fenceAt = tail.indexOf("```");
  const tildeAt = tail.indexOf("~~~");
  const fence =
    fenceAt === -1
      ? tildeAt
      : tildeAt === -1
        ? fenceAt
        : Math.min(fenceAt, tildeAt);
  if (fence === -1) return presentStreamProse(holdBackPendingTableHeader(tail), presented);
  if (fence === 0) return tail;
  return (
    presentStreamProse(tail.slice(0, fence), presented) + tail.slice(fence)
  );
}
