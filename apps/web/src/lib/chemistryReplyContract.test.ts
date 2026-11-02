/**
 * Real chemistry replies from the server (docs/fixtures/chemistry_replies.json), read the way
 * the web reads them. The server's own test proves it still writes exactly these replies.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { CHEMISTRY_ANSWER_NOTATION } from "./answerNotation.ts";
import { prepareAssistantMarkdown } from "./assistantMarkdown.ts";

type Contract = {
  answer_notation: string;
  replies: Record<string, { question: string; reply: string }>;
};

const contract: Contract = JSON.parse(
  readFileSync(new URL("../../../../docs/fixtures/chemistry_replies.json", import.meta.url), "utf8"),
);
const replies = Object.entries(contract.replies);

describe("server chemistry replies", () => {
  it("use the notation header the web strips", () => {
    assert.equal(CHEMISTRY_ANSWER_NOTATION, contract.answer_notation);
  });

  for (const [name, entry] of replies) {
    it(`${name}: shows the answer and never the plumbing`, () => {
      const out = prepareAssistantMarkdown(entry.reply);
      assert.equal(out.includes(contract.answer_notation), false, "notation header leaked");
      assert.equal(out.includes("```chem_scene"), false, "a scene fence was left in");
      assert.equal(out.includes('"kind"'), false, "scene JSON leaked");
      // The first line of the answer is what the reader came for.
      const answer = /```answer\n(?:notation: chemistry\n)?([^\n]+)/.exec(entry.reply)?.[1];
      assert.ok(answer, "the reply has an answer fence");
      assert.ok(out.includes(answer), `the answer "${answer}" is on the page`);
    });
  }
});
