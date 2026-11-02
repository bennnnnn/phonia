import { suggestionToSend, wrapSuggestionMath } from "@/features/suggestions/model/promptMath";

describe("wrapSuggestionMath", () => {
  it("wraps a bare caret equation and leaves the surrounding question", () => {
    expect(
      wrapSuggestionMath(
        "Why does the equation X^2 = 9 have two solutions, +3 and -3, instead of just one?",
      ),
    ).toBe(
      "Why does the equation $X^2 = 9$ have two solutions, +3 and -3, instead of just one?",
    );
  });

  it("wraps each equation in one question", () => {
    expect(
      wrapSuggestionMath(
        "What would the solutions be if the equation was X^2 = 16 instead of X^2 = 9?",
      ),
    ).toBe(
      "What would the solutions be if the equation was $X^2 = 16$ instead of $X^2 = 9$?",
    );
  });

  it("keeps an addition on the same expression", () => {
    expect(
      wrapSuggestionMath("How would you solve the equation X^2 + 4 = 13 using similar steps?"),
    ).toBe("How would you solve the equation $X^2 + 4 = 13$ using similar steps?");
  });

  it("does not wrap a question that is already delimited", () => {
    const ready = "Why does $x^2 = 9$ have two solutions?";
    expect(wrapSuggestionMath(ready)).toBe(ready);
  });

  it("leaves a question with no equation unchanged", () => {
    const plain = "Why does photosynthesis need light?";
    expect(wrapSuggestionMath(plain)).toBe(plain);
  });
});

describe("suggestionToSend", () => {
  it("spaces a tight equation so the letter and the number stay apart", () => {
    expect(suggestionToSend("Why does $x=5$ give a different value?")).toBe(
      "Why does $x = 5$ give a different value?",
    );
  });

  it("sends a fraction when the follow-up lost the f of frac", () => {
    expect(suggestionToSend(String.raw`What is $rac{\sqrt{8}}{2}$ simplified?`)).toBe(
      String.raw`What is $\frac{\sqrt{8}}{2}$ simplified?`,
    );
  });

  // The server keeps these for "3+4" (related_questions._prepare_question); all three show.
  it("keeps a short follow-up that names its numbers", () => {
    expect(suggestionToSend("What is 3 + 5?")).toBe("What is 3 + 5?");
    expect(suggestionToSend("Why does 3 + 4 equal 7?")).toBe("Why does 3 + 4 equal 7?");
    expect(suggestionToSend("Why 3?")).toBeNull();
  });

  it("drops a fragment and a number glued to a letter or a radical", () => {
    expect(suggestionToSend("How")).toBeNull();
    expect(suggestionToSend("Education level")).toBeNull();
    expect(suggestionToSend("What is the value of $x5$ here?")).toBeNull();
    expect(suggestionToSend(String.raw`Why does $^5\sqrt{x} = 0^5$ equal zero?`)).toBeNull();
  });
});
