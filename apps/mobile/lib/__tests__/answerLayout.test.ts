import { splitAnswerBranches } from "@/lib/math/answerLayout";

const first = String.raw`x = 2 \pi k + \frac{\pi}{6}`;
const second = String.raw`\text{ or } x = 2 \pi k + \frac{5 \pi}{6},\quad k \in \mathbb{Z}`;

describe("splitAnswerBranches", () => {
  it("preserves both T05 branches, their OR, and the full integer parameter condition", () => {
    const source = `${first} ${second}`;
    expect(splitAnswerBranches(source)).toEqual([first, second]);
    expect(splitAnswerBranches(source).join(" ")).toBe(source);
  });

  it("also splits explicit plain equation alternatives", () => {
    expect(splitAnswerBranches("x = -2 or x = 2")).toEqual(["x = -2", "or x = 2"]);
  });

  it("handles long whitespace once without changing equation branches", () => {
    expect(splitAnswerBranches(`x = 1${" ".repeat(10000)}or\n x = 2`))
      .toEqual(["x = 1", "or\n x = 2"]);
    expect(splitAnswerBranches("floor = 1 orange = 2")).toEqual(["floor = 1 orange = 2"]);
  });

  it("does not split the text inside a fraction argument", () => {
    const firstBranch = String.raw`x = \frac{\text{a or b}}{2}`;
    expect(splitAnswerBranches(`${firstBranch} ${second}`)).toEqual([firstBranch, second]);
  });

  it.each([
    String.raw`\text{red or blue}`,
    String.raw`\text{x=1} \text{ or } x=2`,
    String.raw`f(x = 1 \text{ or } x = 2)`,
    String.raw`\left|x\right| = 1 \text{ or } x = 2`,
    String.raw`\{x = 1 \text{ or } x = 2\}`,
    String.raw`\begin{cases}x = 1 \text{ or } x = 2\end{cases}`,
    String.raw`x = \frac{1}{2 \text{ or } x = 3`,
    String.raw`x = 1 \text{ or } \mathbb{R}`,
  ])("leaves nested, incomplete, or nonequation content intact: %s", (source) => {
    expect(splitAnswerBranches(source)).toEqual([source]);
  });
});
