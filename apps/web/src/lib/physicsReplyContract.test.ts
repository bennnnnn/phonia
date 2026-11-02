/**
 * Real physics replies from the server (docs/fixtures/physics_replies.json), read the way the
 * web reads them. The server's own test proves it still writes exactly these replies.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { prepareAssistantMarkdown } from "./assistantMarkdown.ts";

type Contract = {
  replies: Record<string, { question: string; answer: string; reply: string }>;
};

const contract: Contract = JSON.parse(
  readFileSync(new URL("../../../../docs/fixtures/physics_replies.json", import.meta.url), "utf8"),
);

describe("server physics replies", () => {
  for (const [name, entry] of Object.entries(contract.replies)) {
    it(`${name}: the answer card reads as the server's plain answer`, () => {
      const out = prepareAssistantMarkdown(entry.reply);
      assert.ok(out.includes(entry.answer), `"${entry.answer}" is not on the page`);
      const card = out.slice(out.lastIndexOf("**Answer**"));
      for (const command of ["\\mathrm", "\\times", "\\text", "\\,", "\\quad", "^\\circ"]) {
        assert.equal(card.includes(command), false, `${command} leaked into the answer`);
      }
    });
  }
});
