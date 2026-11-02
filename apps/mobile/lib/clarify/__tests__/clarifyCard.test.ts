import {
  answersFromMessage,
  asksWithCard,
  clarifyMessage,
  clarifyText,
  initialClarifyAnswers,
  parseClarifyCard,
  type ClarifyCard,
} from "@/lib/clarify/clarifyCard";

// The best-country card from docs/clarify.md, as the server keeps it.
const COUNTRY = JSON.stringify({
  questions: [
    {
      id: "priority",
      label: "Main priority",
      question: "What matters most to you?",
      options: ["💰 Making money", "🌿 Quality of life", "🛡️ Safety"],
      values: ["Making money", "Quality of life", "Safety"],
    },
    {
      id: "region",
      label: "Geographic preference",
      question: "Which region are you considering?",
      options: ["🌍 Anywhere", "🇪🇺 Europe", "🌎 The Americas"],
      values: ["Anywhere", "Europe", "The Americas"],
    },
  ],
  request: "Recommend the best country for me.",
  closing: "Compare the strongest options with practical pros and cons.",
  submit: "Find my best country",
});

// A card saved before cards had values, a request or a button.
const INTEGRALS = JSON.stringify({
  when: "first",
  questions: [
    {
      id: "level",
      label: "Studied it before",
      question: "Have you studied integrals before?",
      options: ["No, never", "A little", "Yes, I'm revising"],
      multi: false,
    },
  ],
});

function card(content = COUNTRY): ClarifyCard {
  const parsed = parseClarifyCard(content);
  if (!parsed) throw new Error("expected a card");
  return parsed;
}

describe("parseClarifyCard", () => {
  it("reads the card the server keeps", () => {
    const parsed = card();
    expect(parsed.questions.map((q) => q.label)).toEqual(["Main priority", "Geographic preference"]);
    expect(parsed.questions[0]!.options).toEqual(["💰 Making money", "🌿 Quality of life", "🛡️ Safety"]);
    expect(parsed.questions[0]!.values).toEqual(["Making money", "Quality of life", "Safety"]);
    expect(parsed).toMatchObject({
      request: "Recommend the best country for me.",
      closing: "Compare the strongest options with practical pros and cons.",
      submit: "Find my best country",
    });
  });

  it("reads an older card: each value is its option, and no request, closing or button", () => {
    const parsed = card(INTEGRALS);
    expect(parsed.questions[0]!.values).toEqual(parsed.questions[0]!.options);
    expect(parsed).toMatchObject({ request: "", closing: "", submit: "" });
  });

  it("says the options when the values do not fit them", () => {
    const parsed = card(
      JSON.stringify({ questions: [{ label: "L", question: "Q?", options: ["a", "b"], values: ["a", ""] }] }),
    );
    expect(parsed.questions[0]!.values).toEqual(["a", "b"]);
  });

  it("fills a missing id or label", () => {
    const parsed = card(JSON.stringify({ questions: [{ question: "Which OS?", options: ["iOS", "Android"] }] }));
    expect(parsed.questions[0]).toMatchObject({ id: "q1", label: "Which OS?" });
  });

  it("drops blank and repeated options, and gives repeated ids new ones", () => {
    const parsed = card(
      JSON.stringify({
        questions: [
          { id: "x", label: "A", question: "A?", options: ["Yes", " yes ", "", "No"] },
          { id: "x", label: "B", question: "B?", options: ["1", "2"] },
        ],
      }),
    );
    expect(parsed.questions[0]!.options).toEqual(["Yes", "No"]);
    expect(parsed.questions.map((q) => q.id)).toEqual(["q1", "q2"]);
  });

  it("keeps eight options", () => {
    const options = ["a", "b", "c", "d", "e", "f", "g", "h"];
    const parsed = card(JSON.stringify({ questions: [{ label: "L", question: "Q?", options }] }));
    expect(parsed.questions[0]!.options).toEqual(options);
  });

  it.each([
    ["not JSON", "Have you studied integrals before?"],
    ["no questions", JSON.stringify({ questions: [] })],
    [
      "four questions",
      JSON.stringify({
        questions: [1, 2, 3, 4].map((n) => ({ label: `L${n}`, question: `Q${n}?`, options: ["a", "b"] })),
      }),
    ],
    ["one option", JSON.stringify({ questions: [{ label: "L", question: "Q?", options: ["a"] }] })],
    [
      "nine options",
      JSON.stringify({ questions: [{ label: "L", question: "Q?", options: "abcdefghi".split("") }] }),
    ],
    ["no question text", JSON.stringify({ questions: [{ label: "L", options: ["a", "b"] }] })],
    ["a question that is not an object", JSON.stringify({ questions: ["Q?"] })],
  ])("refuses %s", (_name, content) => {
    expect(parseClarifyCard(content)).toBeNull();
  });
});

describe("initialClarifyAnswers", () => {
  it("starts every question on its first choice", () => {
    expect(initialClarifyAnswers(card())).toEqual({ priority: 0, region: 0 });
  });
});

describe("clarifyMessage", () => {
  it("writes the request, each label with its pick, then the closing, as the server reads it", () => {
    expect(clarifyMessage(card(), { priority: 0, region: 0 })).toBe(
      "Recommend the best country for me. Main priority: Making money. Geographic preference: " +
        "Anywhere. Compare the strongest options with practical pros and cons.",
    );
  });

  it("says the picked value, without its emoji", () => {
    expect(clarifyMessage(card(), { priority: 2, region: 1 })).toContain(
      "Main priority: Safety. Geographic preference: Europe.",
    );
  });

  it("sends the first choice for a question with no pick", () => {
    expect(clarifyMessage(card(), { region: 2 })).toContain(
      "Main priority: Making money. Geographic preference: The Americas.",
    );
  });

  it("adds no full stop after a pick that ends a sentence, nor an empty request", () => {
    const parsed = card(
      JSON.stringify({ questions: [{ label: "Ready", question: "Ready?", options: ["Yes!", "Not yet"] }] }),
    );
    expect(clarifyMessage(parsed, { q1: 0 })).toBe("Ready: Yes!");
  });

  // "Not sure yet…." and Amharic "አውሮፓ።." read as typos.
  it.each(["Not sure yet…", "አውሮፓ።", "የትኛው፧"])("adds no full stop after %s", (pick) => {
    const parsed = card(
      JSON.stringify({ questions: [{ label: "Pick", question: "Which?", options: [pick, "Other"] }] }),
    );
    expect(clarifyMessage(parsed, { q1: 0 })).toBe(`Pick: ${pick}`);
  });
});

describe("answersFromMessage", () => {
  it("round-trips what the button sends", () => {
    const parsed = card();
    const answers = { priority: 1, region: 2 };
    expect(answersFromMessage(parsed, clarifyMessage(parsed, answers))).toEqual(answers);
  });

  it("reads the one line per question older phones sent", () => {
    expect(answersFromMessage(card(INTEGRALS), "Studied it before: Yes, I'm revising")).toEqual({ level: 2 });
  });

  it("reads the longest choice a pick starts with", () => {
    const parsed = card(
      JSON.stringify({ questions: [{ id: "p", label: "Picked", question: "Which?", options: ["Yes", "Yes, a lot"] }] }),
    );
    expect(answersFromMessage(parsed, "Picked: yes, a lot. Thanks.")).toEqual({ p: 1 });
    expect(answersFromMessage(parsed, "Picked: Yes. Thanks.")).toEqual({ p: 0 });
    expect(answersFromMessage(parsed, "Picked: Yesterday")).toEqual({});
  });

  it("leaves a pick that is none of the choices unticked", () => {
    expect(answersFromMessage(card(), "Main priority: Family. Geographic preference: Europe.")).toEqual({
      region: 1,
    });
  });

  it.each([
    ["anything typed instead", "Just answer"],
    ["a new question", "What about Canada?"],
    ["a label missing", "Main priority: Safety."],
    ["a label inside another word", "Submain priority: Safety. Geographic preference: Europe."],
    ["an empty pick", "Main priority: Safety. Geographic preference:"],
    ["a pick only on the next line", "Main priority:\nGeographic preference: Europe"],
  ])("is null for %s", (_name, message) => {
    expect(answersFromMessage(card(), message)).toBeNull();
  });
});

describe("clarifyText", () => {
  it("is each question with its choices, without emoji", () => {
    expect(clarifyText(card())).toBe(
      "What matters most to you? (Making money / Quality of life / Safety)\n" +
        "Which region are you considering? (Anywhere / Europe / The Americas)",
    );
  });
});

describe("asksWithCard", () => {
  it("is true for a reply that asks with a card", () => {
    expect(asksWithCard(`Two quick questions:\n\n\`\`\`clarify\n${INTEGRALS}\n\`\`\``)).toBe(true);
  });

  it.each([
    ["no card", "Integrals add up tiny pieces."],
    ["a card that does not parse", "Q:\n\n```clarify\n{\"when\": \"first\"}\n```"],
    ["a card still streaming", `Q:\n\n\`\`\`clarify\n${INTEGRALS}`],
  ])("is false for %s", (_name, content) => {
    expect(asksWithCard(content)).toBe(false);
  });
});
