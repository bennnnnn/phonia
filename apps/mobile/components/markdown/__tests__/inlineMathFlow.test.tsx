// Inline maths in a paragraph used to break the line: a raised exponent or a
// bar is a View, the paragraph became a wrapping row of whole Text runs, and
// the prose after the formula jumped to a new line with a gap. These are the
// replies from the answer test (light, limit and sum, scatter fit).
import { render, within } from "@testing-library/react-native";
import { StyleSheet, Text, View, type StyleProp, type TextStyle } from "react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { DisplayRow, InlineFlow } from "@/components/markdown/rules/inlineFlow";
import { MATH_SCRIPT_LINE_HEIGHT } from "@/lib/math/text";

jest.mock("@/components/LinkPreviewCard", () => ({
  LinkPreviewCard: "LinkPreviewCard",
}));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));
jest.mock("@/components/WebPreviewCodeBlock", () => ({
  WebPreviewCodeBlock: "WebPreviewCodeBlock",
}));
jest.mock("@/components/rich/CircularClockBlock", () => ({
  CircularClockBlock: "CircularClockBlock",
}));
jest.mock("@/components/rich/AnswerBlock", () => ({
  AnswerBlock: "AnswerBlock",
}));
// Display math renders via MathJax-SVG now; this suite asserts markdown
// splitting/punctuation, so stand in the native MathText fallback.
jest.mock("@/components/rich/MathSvgView", () => {
  const React = jest.requireActual("react");
  const { MathText } = jest.requireActual("@/components/rich/MathText");
  return {
    MathSvgView: ({ latex }: { latex: string }) => React.createElement(MathText, { latex }),
  };
});
jest.mock("@/components/CodeBlock", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    CodeBlock: ({ code, lang }: { code: string; lang: string }) => (
      <RNText>{`${lang}:${code}`}</RNText>
    ),
  };
});

const LIGHT = String.raw`Light takes approximately **$8.3 \times 10^2$** seconds (about 500 seconds) to travel from the Sun to Earth.`;
const LIMIT = String.raw`The first can be shown by recognizing the expression as the definition of $e$ (the unique number $a$ such that $\lim_{n\to\infty}\left(1+\frac{1}{n}\right)^n = a$, with $e$ equivalently defined by $\lim_{h\to 0}(1+h)^{1/h} = e$). The second was historically significant.`;
const BASEL = String.raw`2. **Series**:
   $\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}$,
   known as the **Basel problem**, famously solved by Euler in 1734.`;
const SCATTER = String.raw`The best-fit line was computed by ordinary least squares. With $\bar{x} = 3$ and $\bar{y} = 6.02$, the slope is $m = 2.01$ and the intercept is $b = 0.06$.`;

function lineHeightOf(element: { props: { style?: StyleProp<TextStyle> } }): number | undefined {
  return StyleSheet.flatten(element.props.style)?.lineHeight;
}

describe("inline maths flows inside the line", () => {
  it("keeps the words after a raised exponent on the formula's line", async () => {
    const { getByTestId, getByText, getByLabelText } = await render(<MarkdownContent content={LIGHT} />);
    const row = getByTestId("md-math-inline-wrap");
    // The exponent is still raised in its own box, and each word is an item
    // that can sit beside it instead of one block of the rest of the sentence.
    expect(within(row).getByTestId("math-text-tall")).toBeOnTheScreen();
    expect(within(row).getByText("seconds")).toBeOnTheScreen();
    expect(within(row).getByText("(about")).toBeOnTheScreen();
    expect(getByLabelText(/^Light takes approximately 8\.3 × 10\^2 seconds \(about 500 seconds\) to travel/)).toBeOnTheScreen();
    // The prose keeps body leading; only the formula's own box is taller.
    expect(lineHeightOf(getByText("travel"))).toBeUndefined();
  });

  it("keeps body line height around a display limit and joins its closing parenthesis", async () => {
    const { getAllByTestId, getByText } = await render(<MarkdownContent content={LIMIT} />);
    const formulas = getAllByTestId("md-heavy-math-run");
    expect(formulas).toHaveLength(2);
    for (const word of ["recognizing", "historically"]) {
      expect(lineHeightOf(getByText(word))).toBeUndefined();
    }
    // ")." closes the parenthetical on the formula, not as the start of the next line.
    expect(within(formulas[1]!).getByText(").")).toBeOnTheScreen();
    expect(getByText("second")).toBeOnTheScreen();
  });

  it("lets a bold phrase and its comma share a line with the prose after a display sum", async () => {
    const { getByTestId, getByText } = await render(<MarkdownContent content={BASEL} />);
    const row = getByTestId("md-math-inline-wrap");
    expect(within(row).getByTestId("md-heavy-math-run")).toHaveStyle({ width: "100%" });
    // "problem" and its comma are one unbreakable Text; "famously" is its own item.
    expect(within(row).getByText(/^problem,$/)).toBeOnTheScreen();
    expect(within(row).getByText("famously")).toBeOnTheScreen();
    expect(lineHeightOf(getByText("famously"))).toBeUndefined();
  });

  it("draws x-bar beside its words, not on a line of its own", async () => {
    const { getByTestId, getByText, getByLabelText } = await render(<MarkdownContent content={SCATTER} />);
    const row = getByTestId("md-math-inline-wrap");
    expect(within(row).getByText("With")).toBeOnTheScreen();
    expect(within(row).getByText("slope")).toBeOnTheScreen();
    expect(getByLabelText(/^The best-fit line was computed by ordinary least squares\. With .+ and .+, the slope is/)).toBeOnTheScreen();
    // The words keep body leading instead of the script line height.
    expect(lineHeightOf(getByText("intercept"))).not.toBe(MATH_SCRIPT_LINE_HEIGHT);
    expect(lineHeightOf(getByText("intercept"))).toBeUndefined();
  });
});

/** The text a formula's math run draws, as the native text engine sees it. */
function mathRunText(node: unknown): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(mathRunText).join("");
  const children = (node as { children?: unknown } | null)?.children;
  return children == null ? "" : mathRunText(children);
}

describe("a formula is one word in the line", () => {
  // "...equal in size ($T = mg$) and opposite..." drew "(T" at the end of a line
  // and "= mg)" on the next: the formula's spaces were break points.
  it.each([
    ["equal in size ($T = mg$) and opposite in direction.", "T\u00a0=\u00a0mg"],
    ["so the forces balance ($F_{net} = 0$) at rest", "0"],
    [String.raw`the sum is $a + b + c + d + e + f + g + h + i + j + k$ in all`, "a\u00a0+\u00a0b"],
  ])("draws %s with no breakable space inside the formula", async (content, piece) => {
    const { getAllByTestId, toJSON } = await render(<MarkdownContent content={content} />);
    const runs = getAllByTestId("math-variable").map((node) => node.parent?.parent ?? node);
    expect(runs.length).toBeGreaterThan(0);
    const drawn = mathRunText(toJSON());
    expect(drawn).toContain(piece);
    for (const run of runs) expect(mathRunText(run.props.children)).not.toMatch(/ /);
  });

  it("keeps a formula one item in a flowing paragraph too", async () => {
    const content = String.raw`Light takes **$8.3 \times 10^2$** s, and ($T = mg$) holds at rest.`;
    const { getByTestId, queryByText, toJSON } = await render(<MarkdownContent content={content} />);
    expect(getByTestId("md-math-inline-wrap")).toBeOnTheScreen();
    // The row splits prose into word items; the formula is not split with it.
    expect(queryByText("=")).toBeNull();
    expect(queryByText("mg)")).toBeNull();
    expect(mathRunText(toJSON())).toContain("T\u00a0=\u00a0mg");
  });
});

describe("InlineFlow", () => {
  const prose = { fontSize: 20, color: "#111" };

  it("gives every word its own item spaced by the font's space", async () => {
    const { getByText } = await render(
      <InlineFlow testID="flow">
        <Text style={prose}>Light takes </Text>
        <View testID="formula" />
        <Text style={prose}> seconds.</Text>
      </InlineFlow>,
    );
    expect(getByText("Light")).toHaveStyle({ marginRight: 5.2, fontSize: 20 });
    expect(getByText("takes")).toHaveStyle({ marginRight: 5.2 });
    expect(getByText("seconds.")).toBeOnTheScreen();
  });

  it("keeps a formula and the punctuation touching it as one box", async () => {
    const { getByTestId } = await render(
      <InlineFlow>
        <Text style={prose}>see (</Text>
        <View testID="formula" />
        <Text style={prose}>). Next</Text>
      </InlineFlow>,
    );
    const unit = getByTestId("formula").parent;
    expect(unit).not.toBeNull();
    expect(within(unit!).getByText("(")).toBeOnTheScreen();
    expect(within(unit!).getByText(").")).toBeOnTheScreen();
    expect(within(unit!).queryByText("Next")).toBeNull();
  });

  it("starts a new row at a line break and gives a display formula its own row", async () => {
    const { getByTestId, getByText, toJSON } = await render(
      <InlineFlow testID="flow">
        <Text>one{"\n"}two</Text>
        <DisplayRow latex="x^2" />
        <Text>three</Text>
      </InlineFlow>,
    );
    expect(getByTestId("md-heavy-math-run")).toHaveStyle({ width: "100%" });
    expect(getByText("one")).toBeOnTheScreen();
    expect(getByText("three")).toBeOnTheScreen();
    expect(JSON.stringify(toJSON())).toContain('"height":0');
  });

  it("flattens a nested flow and keeps an inline code chip whole", async () => {
    const { getAllByTestId, getByTestId, getByText } = await render(
      <InlineFlow testID="outer">
        <InlineFlow testID="inner">
          <Text style={{ fontWeight: "700" }}>bold words </Text>
        </InlineFlow>
        <Text style={{ backgroundColor: "#eee" }}>x_1 costs</Text>
      </InlineFlow>,
    );
    expect(getAllByTestId(/outer|inner/)).toHaveLength(1);
    expect(getByText("bold")).toHaveStyle({ fontWeight: "700" });
    expect(getByText("x_1 costs")).toBeOnTheScreen();
    expect(getByTestId("outer").props.accessibilityLabel).toBe("bold words x_1 costs");
  });

  it("reads as one sentence, unless a link inside needs its own focus", async () => {
    const plain = await render(
      <InlineFlow testID="flow">
        <Text>a b</Text>
      </InlineFlow>,
    );
    expect(plain.getByTestId("flow").props.accessibilityLabel).toBe("a b");
    const linked = await render(
      <InlineFlow testID="flow">
        <Text onPress={() => undefined}>open link</Text>
      </InlineFlow>,
    );
    expect(linked.getByTestId("flow").props.accessible).toBeUndefined();
    expect(linked.getByText("link").props.onPress).toBeDefined();
  });
});
