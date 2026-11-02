import cases from "../../../../docs/fixtures/answer_card_cases.json";

import { splitAnswerNotation } from "@/lib/answerNotation";
import { finalAnswerOnly, splitWorking } from "@/lib/cardValue";

// The server writes cards with the same rule (apps/api/app/services/card_value.py).
describe("answer card value", () => {
  it.each(cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(splitWorking(c.value)).toEqual({ working: c.working, answer: c.answer });
    expect(finalAnswerOnly(c.value)).toBe(c.answer);
  });

  it("an old card that held its calculation shows the final answer alone", () => {
    expect(splitAnswerNotation("verified: true\n1 ÷ 2 + 1 ÷ 3 = \\frac{5}{6}")).toEqual({
      notation: "math",
      body: "\\frac{5}{6}",
      verified: true,
      unchecked: false,
    });
    expect(splitAnswerNotation("notation: chemistry\npH = 2.00").body).toBe("pH = 2.00");
  });
});
