import { attachAnswerHeadingToFence } from "@/lib/markdown/attachAnswerHeading";
import { preprocessMarkdown } from "@/lib/markdown/preprocess";

describe("attachAnswerHeadingToFence", () => {
  it("drops a lone Answer heading above the server's checked card", () => {
    const source = [
      "**1. Divide both sides by 3**",
      "",
      "$x = 0$",
      "",
      "**Answer**",
      "",
      "```answer",
      "verified: true",
      "x = 0",
      "```",
    ].join("\n");

    expect(attachAnswerHeadingToFence(source)).toBe(
      [
        "**1. Divide both sides by 3**",
        "",
        "$x = 0$",
        "",
        "```answer",
        "verified: true",
        "x = 0",
        "```",
      ].join("\n"),
    );
  });

  it.each(["**Answer:**", "## Answer", "Answer:"])(
    "drops %s above an unmarked card too: the card draws its own heading",
    (heading) => {
      const source = `${heading}\n\n\`\`\`answer\nx = 0\n\`\`\``;
      expect(attachAnswerHeadingToFence(source)).toBe("```answer\nx = 0\n```");
    },
  );

  it("leaves Answer in place when no answer fence follows", () => {
    expect(attachAnswerHeadingToFence("**Answer**\n\nThe result is 4.")).toBe(
      "**Answer**\n\nThe result is 4.",
    );
  });
});

describe("preprocessMarkdown answer heading", () => {
  it("keeps Answer out of its own paragraph before the chip", () => {
    const source = "**Given:** $3x = 0$\n\n**Answer**\n\n```answer\nverified: true\nx = 0\n```\n";
    const out = preprocessMarkdown(source);
    expect(out).not.toMatch(/\*\*Answer\*\*/);
    expect(out).toContain("```answer\nverified: true\nx = 0\n```");
  });
});

describe("attachAnswerHeadingToFence: one Answer label", () => {
  const card = "```answer\nx = -\\frac{5}{2}\n```";

  it("drops a heading and its restated value above a card", () => {
    const md = ["**Answer**", "$x = -\\frac{5}{2}$ (or −2.5)", "", card].join("\n");
    expect(attachAnswerHeadingToFence(md)).toBe(card);
  });

  it("drops two headings stacked above a card", () => {
    const md = ["**Answer**", "", "**Answer:**", "", card].join("\n");
    expect(attachAnswerHeadingToFence(md)).toBe(card);
  });

  it("keeps a written-out Answer section with no card below", () => {
    const md = ["**Answer**", "$R = \\frac{346.4}{9.81}$", "$R \\approx 35.3\\ \\text{m}$"].join("\n");
    expect(attachAnswerHeadingToFence(md)).toBe(md);
  });

  it("keeps prose between a heading and the card", () => {
    const md = ["**Answer**", "Only the positive root makes sense for a length.", "", card].join(
      "\n",
    );
    expect(attachAnswerHeadingToFence(md)).toBe(md);
  });
});

describe("attachAnswerHeadingToFence: the follow-up pattern and parts", () => {
  const card = "```answer\nverified: true\n26.3\\,\\mathrm{N·m}\n```";

  it("drops a heading and its 'Answer:' line above a card", () => {
    // A follow-up copied its history: heading, "Answer: …", then the card's own label.
    const md = ["**Answer**", "", String.raw`Answer: 26.3\,\mathrm{N·m}`, "", card].join("\n");
    expect(attachAnswerHeadingToFence(md)).toBe(card);
  });

  it("drops an 'Answer:' line written straight above a card", () => {
    const md = [String.raw`Answer: 26.3\,\mathrm{N·m}`, "", card].join("\n");
    expect(attachAnswerHeadingToFence(md)).toBe(card);
  });

  it("keeps one label with no card: the 'Answer:' line becomes its value, LaTeX as maths", () => {
    const md = ["**Answer**", "", String.raw`Answer: 26.3\,\mathrm{N·m}`, "", "Since τ = Fd…"].join("\n");
    expect(attachAnswerHeadingToFence(md)).toBe(
      ["**Answer**", "", String.raw`$26.3\,\mathrm{N·m}$`, "", "Since τ = Fd…"].join("\n"),
    );
  });

  it.each(["```result", "~~~answer", "````answer", "```Answer"])(
    "drops the heading above every fence the card draws: %s",
    (opener) => {
      const closer = opener.startsWith("~") ? "~~~" : opener.match(/^`+/)?.[0] ?? "```";
      const fence = [opener, "x = 2", closer].join("\n");
      expect(attachAnswerHeadingToFence(["**Answer**", "", fence].join("\n"))).toBe(fence);
    },
  );

  it("gives a part's card its letter, and drops the part's heading", () => {
    const md = ["**Answer (b)**", "", "```answer", "verified: true", "35.3\\,\\mathrm{m}", "```"].join(
      "\n",
    );
    expect(attachAnswerHeadingToFence(md)).toBe(
      ["```answer", "part: b", "verified: true", "35.3\\,\\mathrm{m}", "```"].join("\n"),
    );
  });
});
