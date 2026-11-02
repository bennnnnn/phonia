import {
  citationAuthor,
  detectJsonRichFenceKind,
  parseEmailDraft,
  parseKeyValue,
  parseQuoteAttribution,
  parseSocialPlatform,
  parseSteps,
} from "@/lib/richBlocks";
import { fullEmailText } from "@/features/drafts/model/emailCompose";

describe("detectJsonRichFenceKind", () => {
  it("BUG FIX regression: recognizes a mistagged ```json geometry fence", () => {
    // The model is instructed to use ```geometry (never ```json) for
    // diagrams, but routinely ignores that. Without this detection the
    // fence fell through to a plain syntax-highlighted JSON code block
    // instead of the triangle/rectangle/square diagram it describes.
    const json = JSON.stringify({
      type: "right_triangle",
      base: 4,
      height: 5,
      unit: "cm",
      show_labels: true,
      show_hypotenuse: true,
      show_angle: true,
    });
    expect(detectJsonRichFenceKind(json)).toBe("geometry");
  });

  it("recognizes a mistagged ```json circle fence", () => {
    const json = JSON.stringify({ type: "circle", radius: 4, unit: "cm" });
    expect(detectJsonRichFenceKind(json)).toBe("geometry");
  });

  it("recognizes a mistagged ```json graph fence", () => {
    const json = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: [
        [-2, 4],
        [0, 0],
        [2, 4],
      ],
    });
    expect(detectJsonRichFenceKind(json)).toBe("graph");
  });

  it("returns null for ordinary json that is not a geometry/graph spec", () => {
    expect(detectJsonRichFenceKind(JSON.stringify({ foo: "bar" }))).toBeNull();
  });

  it("returns null for non-JSON content", () => {
    expect(detectJsonRichFenceKind("not json at all")).toBeNull();
  });
});

describe("parseQuoteAttribution", () => {
  it("splits a trailing dash line as the author", () => {
    expect(parseQuoteAttribution("To be or not to be.\n— Shakespeare")).toEqual({
      quote: "To be or not to be.",
      author: "Shakespeare",
    });
  });

  it("needs a newline or a spaced dash — glued em dash stays in the quote", () => {
    expect(parseQuoteAttribution("To be or not to be.— Shakespeare")).toEqual({
      quote: "To be or not to be.— Shakespeare",
    });
  });

  it("splits a trailing spaced em dash on the same line", () => {
    expect(
      parseQuoteAttribution(
        "Courage is the most important of all the virtues. — Maya Angelou",
      ),
    ).toEqual({
      quote: "Courage is the most important of all the virtues.",
      author: "Maya Angelou",
    });
  });

  it("splits a trailing en dash line as the author", () => {
    expect(parseQuoteAttribution("Stay hungry, stay foolish.\n– Steve Jobs")).toEqual({
      quote: "Stay hungry, stay foolish.",
      author: "Steve Jobs",
    });
  });
});

describe("citationAuthor", () => {
  it.each([
    ["— Steve Jobs", "Steve Jobs"],
    ["– Steve Jobs", "Steve Jobs"],
    ["-- Steve Jobs", "Steve Jobs"],
  ])("reads %s as a citation", (line, author) => {
    expect(citationAuthor(line)).toBe(author);
  });

  it("does not read a single hyphen (a bullet) as a citation", () => {
    expect(citationAuthor("- Steve Jobs")).toBeNull();
  });
});

describe("parseEmailDraft", () => {
  it("drops an unsafe placeholder To field but preserves intentional template slots", () => {
    const draft = parseEmailDraft(
      [
        "To: [Manager's Email Address]",
        "Subject: Request for Time Off - [Your Name] - This Friday",
        "",
        "Hi [Manager's Name],",
        "",
        "I would like to request Friday off.",
        "",
        "Best regards,",
        "Bini",
      ].join("\n"),
    );
    expect(draft).toEqual({
      subject: "Request for Time Off - [Your Name] - This Friday",
      body:
        "Hi [Manager's Name],\n\nI would like to request Friday off.\n\nBest regards,\nBini",
    });
    expect(draft?.to).toBeUndefined();
    expect(draft?.body).toContain("[Manager's Name]");
  });

  it("round-trips a send-ready draft through fullEmailText", () => {
    const source = {
      to: "jane@work.com",
      subject: "Friday off",
      body: "Hi Jane,\n\nSee you then.",
    };
    expect(parseEmailDraft(fullEmailText(source))).toEqual(source);
  });

  it("keeps a real To address and markdown links in the body", () => {
    const draft = parseEmailDraft(
      [
        "To: jane@work.com",
        "Subject: Friday off",
        "",
        "Hi Jane,",
        "",
        "See [the policy](https://example.com/pto).",
      ].join("\n"),
    );
    expect(draft).toEqual({
      to: "jane@work.com",
      subject: "Friday off",
      body: "Hi Jane,\n\nSee [the policy](https://example.com/pto).",
    });
  });

  it.each([
    ["Para: ana@example.com", "Asunto: Vacaciones"],
    ["À: jean@example.fr", "Objet: Vacances"],
    ["An: ida@example.de", "Betreff: Urlaub"],
    ["Kime: ada@example.com", "Konu: Tatil"],
    ["ለ: hana@example.com", "ርዕስ: ዕረፍት"],
    ["收件人: li@example.cn", "主题: 假期"],
    ["宛先: aiko@example.jp", "件名: 休暇"],
    ["받는 사람: min@example.kr", "제목: 휴가"],
  ])("parses localized email headers: %s / %s", (toLine, subjectLine) => {
    const draft = parseEmailDraft(`${toLine}\n${subjectLine}\n\nHello team,\n\nBody.`);
    expect(draft).toEqual({
      to: toLine.slice(toLine.indexOf(":") + 1).trim(),
      subject: subjectLine.slice(subjectLine.indexOf(":") + 1).trim(),
      body: "Hello team,\n\nBody.",
    });
  });
});

describe("parseKeyValue", () => {
  it("returns rows for key: value lines", () => {
    expect(parseKeyValue("Name: Ada\nRole: Engineer")).toEqual([
      { key: "Name", value: "Ada" },
      { key: "Role", value: "Engineer" },
    ]);
  });

  it("fails closed on garbage", () => {
    expect(parseKeyValue("just a paragraph\nno pairs here")).toEqual([]);
    expect(parseKeyValue(":")).toEqual([]);
    expect(parseKeyValue("")).toEqual([]);
  });
});

describe("parseSteps", () => {
  it("keeps numbered and bulleted steps", () => {
    expect(parseSteps("1. Mix\n2. Bake\n- Cool")).toEqual(["Mix", "Bake", "Cool"]);
  });

  it("fails closed on unstructured prose", () => {
    expect(parseSteps("Just mix and bake until done.")).toEqual([]);
  });

  it("keeps a plain line under a step as part of it", () => {
    expect(
      parseSteps("1. **Read `2` at index `0`**\n   We need `7`.\n   Dictionary: `{2: 0}`\n2. Read `7`"),
    ).toEqual(["**Read `2` at index `0`**\nWe need `7`.\nDictionary: `{2: 0}`", "Read `7`"]);
  });
});

describe("parseSocialPlatform", () => {
  it("maps facebook and instagram tags to those cards", () => {
    expect(parseSocialPlatform("facebook")).toBe("facebook");
    expect(parseSocialPlatform("fb")).toBe("facebook");
    expect(parseSocialPlatform("instagram")).toBe("instagram");
    expect(parseSocialPlatform("ig")).toBe("instagram");
  });

  it("maps other social aliases to a generic post card", () => {
    expect(parseSocialPlatform("social")).toBe("generic");
    expect(parseSocialPlatform("tiktok")).toBe("generic");
    expect(parseSocialPlatform("caption")).toBe("generic");
  });

  it("returns null for programming languages", () => {
    expect(parseSocialPlatform("python")).toBeNull();
  });
});
