/**
 * Real physics replies from the server (docs/fixtures/physics_replies.json), read the way the
 * app reads them. The server's own test proves it still writes exactly these replies.
 */
import { splitAnswerNotation } from "@/lib/answerNotation";
import { markdownToCopyText, markdownToSpeechText } from "@/lib/markdown/plain";
import { readableLatexFallback } from "@/lib/math/text";

import fixture from "../../../../docs/fixtures/physics_replies.json";

type Contract = {
  replies: Record<string, { question: string; answer: string; reply: string }>;
};

const contract: Contract = fixture;
const replies = Object.entries(contract.replies);

function answerCard(reply: string): string {
  const open = "```answer\n";
  const start = reply.indexOf(open) + open.length;
  return reply.slice(start, reply.indexOf("\n```", start));
}

describe("server physics replies", () => {
  it.each(replies)("%s: the answer card is typeset, not chemistry text", (_name, entry) => {
    const { notation, body } = splitAnswerNotation(answerCard(entry.reply));
    expect(notation).not.toBe("chemistry");
    // A dimensionless answer can be valid math with no TeX command (MA = 5).
    expect(body.includes("\\") || /^[-+]?\d+(?:\.\d+)?$/.test(body.trim())).toBe(true);
  });

  it.each(replies)("%s: the readable fallback has no raw commands", (_name, entry) => {
    expect(readableLatexFallback(answerCard(entry.reply))).not.toMatch(/\\[A-Za-z,]/);
  });

  it.each(replies)("%s: copy and read-aloud carry the answer's numbers", (_name, entry) => {
    const numbers = entry.answer.match(/\d+(?:\.\d+)?/g) ?? [];
    for (const text of [markdownToCopyText(entry.reply), markdownToSpeechText(entry.reply)]) {
      for (const number of numbers) expect(text).toContain(number);
      expect(text).not.toContain("\\mathrm");
    }
  });

  it.each(replies)("%s: as sent, the card is checked and the marker is never read", (_name, entry) => {
    // The server marks a direct reply's cards when it sends them.
    const sent = entry.reply.replaceAll("```answer\n", "```answer\nverified: true\n");
    const parsed = splitAnswerNotation(answerCard(sent));
    expect(parsed.verified).toBe(true);
    expect(parsed.body).toBe(splitAnswerNotation(answerCard(entry.reply)).body);
    for (const text of [markdownToCopyText(sent), markdownToSpeechText(sent)]) {
      expect(text).not.toContain("verified");
    }
  });

  it("reads degrees as degrees, not as a power", () => {
    const { reply } = contract.replies.launch_angles!;
    expect(markdownToCopyText(reply)).toContain("23.7° or 66.3°");
    expect(markdownToSpeechText(reply)).toContain("23.7 degrees or 66.3 degrees");
    expect(markdownToSpeechText(reply)).not.toContain("power of ∘");
  });
});
