import { arrayCardText, quizCardText } from "@/lib/lesson/cardBody";
import {
  arrayText,
  explanationParts,
  formatCell,
  looseArray,
  looseQuiz,
  optionLetter,
  parseArrayFence,
  parseQuizFence,
  plainFenceText,
  quizText,
} from "@/lib/lesson/lessonFences";

const QUIZ = {
  question: "What should `two_sum(nums, target)` return?",
  options: ["`[0, 1]`", "`[1, 2]`", "`[0, 2]`", "`[2, 4]`"],
  answer: 1,
  explanation: "`2 + 4 = 6`, at indexes 1 and 2.",
};

describe("parseQuizFence", () => {
  it("reads the question, options, answer and explanation", () => {
    expect(parseQuizFence(JSON.stringify(QUIZ))).toEqual({
      ...QUIZ,
      label: null,
      code: null,
      codeLang: "python",
    });
  });

  it("reads the label and the code drawn inside the card", () => {
    const fence = parseQuizFence(
      JSON.stringify({
        ...QUIZ,
        label: "Exercise 1",
        code: "\nnumbers = [2, 4]\nprint(numbers)\n",
        lang: "javascript",
      }),
    );
    expect(fence).toMatchObject({
      label: "Exercise 1",
      code: "numbers = [2, 4]\nprint(numbers)",
      codeLang: "javascript",
    });
    expect(quizText(fence!)).toBe(
      "What should `two_sum(nums, target)` return?\nnumbers = [2, 4]\nprint(numbers)\n" +
        "A) `[0, 1]`\nB) `[1, 2]`\nC) `[0, 2]`\nD) `[2, 4]`",
    );
  });

  it.each([
    ["B", 1],
    ["b)", 1],
    ["2", 2],
    ["`[0, 2]`", 2],
  ])("reads the answer %p as option %p", (answer, index) => {
    expect(parseQuizFence(JSON.stringify({ ...QUIZ, answer }))?.answer).toBe(
      index,
    );
  });

  it.each([
    ["not json", "{question"],
    ["no question", JSON.stringify({ ...QUIZ, question: " " })],
    ["one option", JSON.stringify({ ...QUIZ, options: ["only"] })],
    ["an empty option", JSON.stringify({ ...QUIZ, options: ["a", ""] })],
    ["answer out of range", JSON.stringify({ ...QUIZ, answer: 4 })],
    ["unknown answer", JSON.stringify({ ...QUIZ, answer: "the second" })],
  ])("returns null for %s", (_, content) => {
    expect(parseQuizFence(content)).toBeNull();
  });

  it("writes the question and lettered options as text", () => {
    expect(quizText(parseQuizFence(JSON.stringify(QUIZ))!)).toBe(
      "What should `two_sum(nums, target)` return?\nA) `[0, 1]`\nB) `[1, 2]`\nC) `[0, 2]`\nD) `[2, 4]`",
    );
  });
});

describe("parseArrayFence", () => {
  it("reads the name, values and highlighted indexes", () => {
    const fence = parseArrayFence(
      '{"name":"nums","values":[2,7,11,15],"highlight":[0,1,9]}',
    );
    expect(fence).toEqual({
      name: "nums",
      title: null,
      values: [2, 7, 11, 15],
      highlight: [0, 1],
      caption: null,
      note: null,
    });
    expect(arrayText(fence!)).toBe("nums = [2, 7, 11, 15]");
  });

  it("quotes strings and keeps the rest as written", () => {
    expect(formatCell("a")).toBe('"a"');
    expect(formatCell(3.5)).toBe("3.5");
    expect(formatCell(true)).toBe("true");
    expect(arrayText(parseArrayFence('{"values":["a",null]}')!)).toBe(
      '["a", null]',
    );
  });

  it.each([
    ["not json", "[1, 2"],
    ["no values", '{"name":"nums"}'],
    ["empty", '{"values":[]}'],
    ["nested", '{"values":[[1]]}'],
  ])("returns null for %s", (_, content) => {
    expect(parseArrayFence(content)).toBeNull();
  });
});

describe("explanationParts", () => {
  it("splits prose and fenced code in order", () => {
    expect(
      explanationParts(
        "`enumerate()` gives both.\n\n```python\nprint(1)\n```\n\nThen 1 prints.",
      ),
    ).toEqual([
      { kind: "text", text: "`enumerate()` gives both." },
      { kind: "code", lang: "python", code: "print(1)" },
      { kind: "text", text: "Then 1 prints." },
    ]);
  });

  it("keeps plain prose whole", () => {
    expect(explanationParts("Only 6 and 8.")).toEqual([
      { kind: "text", text: "Only 6 and 8." },
    ]);
    expect(explanationParts("")).toEqual([]);
  });
});

describe("looseQuiz", () => {
  it("reads the words from JSON that does not parse", () => {
    const broken =
      '{"question": "Pick \\"one\\"", "options": ["a", 2, "b",], "answer": 9,\n' +
      '"explanation": "Line one\nline two"}';
    expect(looseQuiz(broken)).toEqual({
      label: null,
      question: 'Pick "one"',
      code: null,
      codeLang: "python",
      options: ["a", "2", "b"],
      explanation: "Line one\nline two",
    });
  });

  it("is null when there is no question and no options", () => {
    expect(looseQuiz('{"note": "x"}')).toBeNull();
    expect(looseQuiz('{"options": []}')).toBeNull();
  });

  it("keeps options it reached when the array never closes", () => {
    expect(looseQuiz('{"question": "Q", "options": ["a", "b"')?.options).toEqual([
      "a",
      "b",
    ]);
  });
});

describe("looseArray", () => {
  it("reads values and lines from JSON that does not parse", () => {
    expect(
      looseArray('{"values": [1, "two", true, null,], "note": "n", "caption": "c",}'),
    ).toEqual({ values: ["1", "two", "true", "null"], title: null, caption: "c", note: "n" });
  });

  it("is null without values", () => {
    expect(looseArray('{"values": []}')).toBeNull();
    expect(looseArray('{"title": "t"}')).toBeNull();
  });
});

describe("plainFenceText", () => {
  it("returns text that is not JSON", () => {
    expect(plainFenceText("  Which loop prints 1 to 5?  ")).toBe("Which loop prints 1 to 5?");
    expect(plainFenceText('{"question": "Q"}')).toBeNull();
    expect(plainFenceText("[1, 2]")).toBeNull();
    expect(plainFenceText("   ")).toBeNull();
  });

  it("is not plain when JSON follows a line of prose, so the answer key never shows as text", () => {
    const keyed = 'Here you go:\n{"question":"Q","options":["a","b"],"answer":1,"explanation":"secret"}';
    expect(plainFenceText(keyed)).toBeNull();
    expect(plainFenceText('Here: {"values": [1, 2]}')).toBeNull();
    for (const question of [
      "Is {1, 2} a subset of [1, 2, 3]?",
      'Given x = {"a": 1}, what is x["a"]?',
      'Translate "hola": what does it mean?',
    ]) {
      expect(plainFenceText(question)).toBe(question);
    }
  });
});

describe("what a card's copy reads", () => {
  it("reads a quiz as its card shows it, before Check answer", () => {
    expect(quizCardText(JSON.stringify(QUIZ))).toBe(
      "What should `two_sum(nums, target)` return?\nA) `[0, 1]`\nB) `[1, 2]`\nC) `[0, 2]`\nD) `[2, 4]`",
    );
    expect(quizCardText("Which loop prints 1 to 5?")).toBe("Which loop prints 1 to 5?");
    const broken = '{"question": "Pick", "options": ["a", "b",], "answer": 1, "explanation": "secret"}';
    expect(quizCardText(broken)).toBe("Pick\nA) a\nB) b");
    expect(quizCardText('{"label": "Card 1", "question": "hablar", "explanation": "to speak"}')).toBe(
      "hablar",
    );
  });

  it("reads nothing for a quiz still streaming in or holding JSON after prose", () => {
    expect(quizCardText('{"question": "What will')).toBe("");
    expect(
      quizCardText('Here you go:\n{"question":"Q","options":["a","b"],"answer":1,"explanation":"secret"}'),
    ).toBe("");
  });

  it("reads a list as its card shows it", () => {
    expect(arrayCardText('{"name": "nums", "values": [2, 7]}')).toBe("nums = [2, 7]");
    expect(arrayCardText('{"values": [1, "two",], "note": "n"}')).toBe("[1, two]");
    expect(arrayCardText('{"values": [1, 2')).toBe("");
  });
});

describe("optionLetter", () => {
  it("letters the first six options and numbers the rest", () => {
    expect(optionLetter(0)).toBe("A)");
    expect(optionLetter(5)).toBe("F)");
    expect(optionLetter(6)).toBe("7)");
  });
});
