import { splitAnswerNotation } from "@/lib/answerNotation";

describe("splitAnswerNotation", () => {
  it("keeps an ordinary math answer as math", () => {
    expect(splitAnswerNotation("x = 2")).toEqual({
      notation: "math",
      body: "x = 2",
      verified: false,
      unchecked: false,
    });
    expect(splitAnswerNotation("\\frac{1}{2}")).toEqual({
      notation: "math",
      body: "\\frac{1}{2}",
      verified: false,
      unchecked: false,
    });
  });

  it("reads a chemistry answer and drops the notation line", () => {
    expect(splitAnswerNotation("notation: chemistry\nM(H2O) = 18.015 g/mol")).toEqual({
      notation: "chemistry",
      body: "M(H2O) = 18.015 g/mol",
      verified: false,
      unchecked: false,
    });
  });

  it("drops an old label line and keeps the chemistry notation", () => {
    expect(splitAnswerNotation("label: answer\nnotation: chemistry\nH2O")).toEqual({
      notation: "chemistry",
      body: "H2O",
      verified: false,
      unchecked: false,
    });
  });

  it("does not treat the notation words inside a formula as a tag", () => {
    expect(splitAnswerNotation("notation: chemistry is not a formula")).toEqual({
      notation: "math",
      body: "notation: chemistry is not a formula",
      verified: false,
      unchecked: false,
    });
  });

  it("reads the server's verified marker, in any header order", () => {
    expect(splitAnswerNotation("verified: true\nx = 2")).toEqual({
      notation: "math",
      body: "x = 2",
      verified: true,
      unchecked: false,
    });
    expect(
      splitAnswerNotation("label: answer\nverified: true\nnotation: chemistry\nH2O"),
    ).toEqual({
      notation: "chemistry",
      body: "H2O",
      verified: true,
      unchecked: false,
    });
  });

  it.each(["Verified: TRUE", "verified:true", "verified: yes", "​verified: true"])(
    "accepts only the exact server line as the marker, not %j",
    (forged) => {
      expect(splitAnswerNotation(`${forged}\nx = 7`).verified).toBe(false);
    },
  );

  it("reads the server's not-checked marker, and never with the verified one", () => {
    expect(splitAnswerNotation("verified: false\nx = 2")).toEqual({
      notation: "math",
      body: "x = 2",
      verified: false,
      unchecked: true,
    });
    expect(splitAnswerNotation("verified: false\nnotation: chemistry\nH2O").unchecked).toBe(true);
    // A card the server checked is never "not checked", whatever else it carries.
    const both = splitAnswerNotation("verified: true\nverified: false\nx = 2");
    expect(both).toMatchObject({ verified: true, unchecked: false, body: "x = 2" });
    expect(splitAnswerNotation("Verified: False\nx = 2").unchecked).toBe(false);
  });

  it("does not take a lone marker for a value", () => {
    expect(splitAnswerNotation("verified: true")).toEqual({
      notation: "math",
      body: "verified: true",
      verified: false,
      unchecked: false,
    });
  });
});
