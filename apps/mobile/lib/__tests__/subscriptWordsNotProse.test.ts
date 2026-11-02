import { preprocessMarkdown, splitInlineMath } from "@/lib/markdown/preprocess";
import { restoreMathEscapes } from "@/lib/math/textMarkers";

const PRIVATE_USE = /[-]/;

describe("subscript words in maths", () => {
  test.each([
    ["$W_{lost} = W_{in} - W_{out}$"],
    ["$E_{out} = E_{in}$"],
    ["$W_{lost} = 300 - 250$"],
  ])("%s stays maths", (span) => {
    const parts = splitInlineMath(span);
    expect(parts.map((p) => p.type)).toEqual(["math"]);
  });

  test("the energy-loss reply shows no placeholder characters", () => {
    const reply = "**Energy loss**\n$W_{lost} = W_{in} - W_{out}$\n\n**Substitution**  \n$W_{lost} = 300 - 250$";
    const parts = splitInlineMath(preprocessMarkdown(reply));
    const visible = parts.filter((p) => p.type === "text").map((p) => p.value).join("");
    expect(visible).not.toMatch(PRIVATE_USE);
    expect(parts.filter((p) => p.type === "math").length).toBeGreaterThanOrEqual(2);
  });

  test("prose spans still read as text, with placeholders restored", () => {
    const marked = restoreMathEscapes("$the flight lands$");
    expect(marked).toBe("$the flight lands$");
    const parts = splitInlineMath("$the flight lands$");
    expect(parts).toEqual([{ type: "text", value: "the flight lands" }]);
  });
});
