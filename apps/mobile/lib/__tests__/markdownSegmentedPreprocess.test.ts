/**
 * The streaming preprocess cuts a reply's closed text into parts and
 * preprocesses each once (lib/markdown/segmentedPreprocess.ts). At every line
 * of every reply here it must give exactly what `preprocessMarkdown` gives the
 * whole stable prefix, as it did before it was cut.
 */
import * as preprocess from "@/lib/markdown/preprocess";
import { preprocessMarkdown } from "@/lib/markdown/preprocess";
import {
  findStableMarkdownPrefixLen,
  preprocessMarkdownForStream,
  preprocessSettledMarkdown,
  type StreamingPreprocessCache,
} from "@/lib/markdown/preprocessStream";
import { presentStreamTail } from "@/lib/markdown/presentation";
import { formatAssistantMathExpr } from "@/lib/math/formatInput";
import { STREAMING_REPLIES } from "@/lib/__tests__/fixtures/streamingReplies";

import chemistry from "../../../../docs/fixtures/chemistry_replies.json";
import physics from "../../../../docs/fixtures/physics_replies.json";
import presentation from "../../../../docs/fixtures/presentation_cases.json";
import chatCode from "../../../api/app/tests/behavior/sweep_corpus/chat_code.json";
import followups from "../../../api/app/tests/behavior/sweep_corpus/followups.json";
import lifeAdmin from "../../../api/app/tests/behavior/sweep_corpus/life_admin.json";
import mathScience from "../../../api/app/tests/behavior/sweep_corpus/math_science.json";
import wordProblems from "../../../api/app/tests/behavior/sweep_corpus/stem_word_problems.json";
import writing from "../../../api/app/tests/behavior/sweep_corpus/writing.json";

type Reply = [name: string, text: string];

const sweep: Reply[] = [chatCode, followups, lifeAdmin, mathScience, wordProblems, writing]
  .flat()
  .flatMap((turn: { id: string; reply?: string }): Reply[] =>
    typeof turn.reply === "string" ? [[turn.id, turn.reply]] : [],
  );

const replies: Reply[] = [
  ...Object.entries(STREAMING_REPLIES),
  ...Object.entries(physics.replies).map(([name, entry]): Reply => [name, entry.reply]),
  ...Object.entries(chemistry.replies).map(([name, entry]): Reply => [name, entry.reply]),
  ...presentation.cases.map((c): Reply => [c.id, c.input]),
  ...sweep,
];

/** Long replies: runs of corpus replies, one after another. */
const longReplies: Reply[] = Array.from({ length: 8 }, (_, i): Reply => {
  const run = sweep.slice(i * 6, i * 6 + 6).map(([, text]) => text);
  return [`run-${i}`, run.join("\n\n")];
});

function lineEnds(text: string): number[] {
  const ends: number[] = [];
  for (let i = text.indexOf("\n"); i >= 0; i = text.indexOf("\n", i + 1)) ends.push(i + 1);
  ends.push(text.length);
  return ends;
}

/** What the stream preprocess gave before it was cut: the whole stable prefix, then the tail. */
function wholePrefix(content: string, presented: boolean): string {
  const stable = findStableMarkdownPrefixLen(content);
  const head = stable > 0
    ? preprocessMarkdown(content.slice(0, stable), formatAssistantMathExpr, { presented })
    : "";
  return head + presentStreamTail(content.slice(stable), presented);
}

/** Stream `text` a line at a time; the first line where the two differ, or null. */
function firstDifference(text: string, presented = false): string | null {
  let cache: StreamingPreprocessCache | null = null;
  for (const end of lineEnds(text)) {
    const content = text.slice(0, end);
    const streamed = preprocessMarkdownForStream(content, cache, formatAssistantMathExpr, {
      presented,
    });
    cache = streamed.cache;
    if (streamed.prepared !== wholePrefix(content, presented)) return content;
  }
  return null;
}

function partsOf(text: string): number {
  let cache: StreamingPreprocessCache | null = null;
  for (const end of lineEnds(text)) {
    cache = preprocessMarkdownForStream(text.slice(0, end), cache, formatAssistantMathExpr).cache;
  }
  return (cache?.segments?.starts.length ?? 0) + 1;
}

describe("preprocessing a stream in parts", () => {
  it("gives every corpus reply, at every line, what the whole prefix gives", () => {
    const differ = replies.filter(([, text]) => firstDifference(text) !== null).map(([name]) => name);
    expect(differ).toEqual([]);
  });

  it("gives long replies, at every line, what the whole prefix gives", () => {
    const differ = longReplies.filter(([, text]) => firstDifference(text) !== null);
    expect(differ.map(([name]) => name)).toEqual([]);
  });

  it("gives a saved row held in stream layout what the whole prefix gives", () => {
    for (const [name, text] of Object.entries(STREAMING_REPLIES)) {
      expect({ name, at: firstDifference(text, true) }).toEqual({ name, at: null });
    }
  });

  it("reads a worked region again when its Given label arrives after a bold label", () => {
    const text = [
      "Here is the working.",
      "",
      "**Speed**",
      "$v = d / t$",
      "",
      "A paragraph between the two.",
      "",
      "**Given**",
      "$d = 10$",
      "",
      "**Required**",
      "$v$",
      "",
      "Done.",
      "",
    ].join("\n");
    expect(firstDifference(text)).toBeNull();
  });

  it("cuts long replies into many parts", () => {
    expect(partsOf(STREAMING_REPLIES.maths)).toBeGreaterThanOrEqual(10);
    expect(partsOf(physics.replies.projectile_parts.reply)).toBeGreaterThanOrEqual(8);
    expect(partsOf(STREAMING_REPLIES.tips)).toBeGreaterThanOrEqual(3);
  });
});

/** The cache a reply's stream ends with, streamed a line at a time up to `draft`. */
function streamedCache(draft: string): StreamingPreprocessCache | null {
  let cache: StreamingPreprocessCache | null = null;
  for (const end of lineEnds(draft)) {
    cache = preprocessMarkdownForStream(draft.slice(0, end), cache, formatAssistantMathExpr).cache;
  }
  return cache;
}

/** Where settling `saved` after streaming `draft` differs from preprocessing it whole. */
function settleDifference(draft: string, saved: string): string | null {
  const settled = preprocessSettledMarkdown(saved, streamedCache(draft), formatAssistantMathExpr);
  return settled === preprocessMarkdown(saved, formatAssistantMathExpr) ? null : saved;
}

describe("settling a streamed reply", () => {
  const all = [...replies, ...longReplies];

  it("gives every corpus reply what preprocessing it whole gives", () => {
    // Saved as streamed, and as the server keeps it: trimmed, its last line open.
    const differ = all.filter(
      ([, text]) => settleDifference(text, text) !== null || settleDifference(text, text.trim()) !== null,
    );
    expect(differ.map(([name]) => name)).toEqual([]);
  });

  it("gives a saved reply that differs from its stream what preprocessing it whole gives", () => {
    const differ = all.filter(([, text]) => {
      const lines = text.trim().split("\n");
      const cut = Math.floor(lines.length / 2);
      // The stream stopped early, the server added a closing note, or a line changed mid-reply.
      const shorter = lines.slice(0, cut).join("\n");
      const appended = `${text.trim()}\n\n**Given** the note above, that is the answer.`;
      const edited = [...lines.slice(0, cut), "A line the server rewrote.", ...lines.slice(cut + 1)].join("\n");
      return [
        settleDifference(shorter, text.trim()),
        settleDifference(text, appended),
        settleDifference(text, edited),
      ].some((at) => at !== null);
    });
    expect(differ.map(([name]) => name)).toEqual([]);
  });

  it("preprocesses the text after the last cut, not the whole reply", () => {
    const long = longReplies.map(([, text]) => text.trim()).join("\n\n");
    const cache = streamedCache(long);
    const whole = preprocessMarkdown(long, formatAssistantMathExpr);
    const read = jest.spyOn(preprocess, "preprocessMarkdown");
    expect(preprocessSettledMarkdown(long, cache, formatAssistantMathExpr)).toBe(whole);
    const chars = read.mock.calls.reduce((sum, [text]) => sum + text.length, 0);
    read.mockRestore();
    // It preprocessed all of it again.
    expect(chars).toBeLessThan(long.length / 10);
  });
});
