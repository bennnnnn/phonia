import {
  isAnswerHeading,
  isSolutionHeading,
  isWorkedReply,
  lawHeading,
  splitWorkoutNote,
  workoutHeading,
} from "@/lib/markdown/workoutSection";

describe("splitWorkoutNote", () => {
  it.each([
    ["$2x = 8$ — subtract 3", { state: "$2x = 8$", note: "subtract 3" }],
    ["$a — b$ — a dash inside math stays math", { state: "$a — b$", note: "a dash inside math stays math" }],
    ["Every step checks out.", { state: "Every step checks out.", note: null }],
    ["$x > 0$ — domain for $x$", { state: "$x > 0$", note: "domain for $x$" }],
  ])("%s", (line, expected) => {
    expect(splitWorkoutNote(line)).toEqual(expected);
  });
});

describe("isSolutionHeading", () => {
  it.each([
    ["Solution", true],
    ["Solution:", true],
    [" Solution ", true],
    ["Solutions", false],
    ["Formula", false],
  ])("%s", (text, expected) => {
    expect(isSolutionHeading(text)).toBe(expected);
  });
});

describe("workoutHeading", () => {
  it.each([
    ["Given", "Given"],
    ["Required", "Required"],
    // A reply written before November 2026 headed what is asked "Find".
    ["Find", "Find"],
    ["Steps:", "Steps"],
    ["Substitution", "Substitution"],
    ["Diagram", null],
    ["1. Subtract 3", null],
    ["Answer (a)", "Answer (a)"],
    ["Answer (z)", null],
  ])("%s", (text, expected) => {
    expect(workoutHeading(text)).toBe(expected);
  });

  it.each([
    ["**Given**  \n$v = 25$", true],
    ["**Required**  \n$t$", true],
    ["**Find**  \n$t$", true],
    ["**Requirements**  \nNode 18", false],
    ["What is required to find $t$?", false],
  ])("reads %j as worked: %s", (text, expected) => {
    expect(isWorkedReply(text)).toBe(expected);
  });

  it("reads one part's answer as an answer", () => {
    expect(isAnswerHeading("Answer")).toBe(true);
    expect(isAnswerHeading("Answer (b)")).toBe(true);
    expect(isAnswerHeading("Answers")).toBe(false);
  });
});

describe("lawHeading", () => {
  it.each([
    ["Constant acceleration", "$v = u + at$", "Constant acceleration"],
    ["Newton's second law", "$F = ma$ — net force", "Newton's second law"],
    // Not a heading over maths: a sentence, a numbered move, a part, or no maths below.
    ["Now solve for a.", "$a = 2$", null],
    ["1. Subtract 4 from both sides", "$2x = 8$", null],
    ["(a) Time in the air", "$t = 2$", null],
    ["Constant acceleration", "The car speeds up evenly.", null],
    ["Ideal mechanical advantage of a wheel and axle", "$\mathrm{IMA} = R/r$", "Ideal mechanical advantage of a wheel and axle"],
    ["A heading that runs far too long to be the name of one law", "$x$", null],
  ])("%s over %s", (text, firstLine, expected) => {
    expect(lawHeading(text, firstLine)).toBe(expected);
  });
});
