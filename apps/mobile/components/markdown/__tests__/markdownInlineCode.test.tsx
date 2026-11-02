import { render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { inlineCodeTextStyle } from "@/components/markdown/markdownContentStyles";
import { ChipText } from "@/components/rich/ChipText";
import { RichMathBody } from "@/components/rich/RichMathBody";
import { CODE_FONT, MATH_FONT } from "@/lib/fonts";
import { darkTheme, lightTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

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
jest.mock("@/components/CodeBlock", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    CodeBlock: ({ code, lang }: { code: string; lang: string }) => (
      <RNText>{`${lang}:${code}`}</RNText>
    ),
  };
});

type Node = { type: string; props: Record<string, unknown>; children: (Node | string)[] | null };

function strings(node: Node | Node[] | string | null): string {
  if (node == null) return "";
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(strings).join("");
  return (node.children ?? []).map(strings).join("");
}

/** The outermost Texts drawn in one face, in reading order. */
function spansInFace(
  node: Node | Node[] | string | null,
  family: string,
  out: Node[] = [],
): Node[] {
  if (node == null || typeof node === "string") return out;
  if (Array.isArray(node)) {
    node.forEach((child) => spansInFace(child, family, out));
    return out;
  }
  const flat = StyleSheet.flatten(node.props.style as never) as { fontFamily?: string } | undefined;
  if (node.type === "Text" && flat?.fontFamily === family) {
    out.push(node);
    return out;
  }
  (node.children ?? []).forEach((child) => spansInFace(child, family, out));
  return out;
}

const visible = (text: string) => text.replace(/ /g, "");

const ITERATION =
  "- **Iteration 1**: `n` is $2$. `total += n` means `total = total + n`. So, `total` becomes $0 + 2 = 2$.";

describe("inline code in a reply", () => {
  it("draws the reported iteration line as code pills and two formulas", async () => {
    const view = await render(<MarkdownContent content={ITERATION} />);
    const tree = view.toJSON() as Node;
    expect(spansInFace(tree, CODE_FONT).map((span) => visible(strings(span)))).toEqual([
      "n",
      "total += n",
      "total = total + n",
      "total",
    ]);
    // A formula's spaces are no-break spaces, so it never wraps mid-formula.
    expect(spansInFace(tree, MATH_FONT).map((span) => strings(span).replace(/\u00a0/g, " "))).toEqual([
      "2",
      "0 + 2 = 2",
    ]);
    expect(visible(strings(tree))).not.toMatch(/[$`]/);
  });

  it.each([
    "The value $`total`$ is 2.",
    "`total` is `$5` and `x$` then $y = 2$.",
    "**Line 1:** `total = 0`\nCreates a variable `total` and sets it to `0`.",
    "1. `IndexError` when you read `numbers[2]`\n2. **Final output:** `12`",
  ])("shows no stray backtick for %s", async (content) => {
    const view = await render(<MarkdownContent content={content} />);
    expect(strings(view.toJSON() as Node)).not.toContain("`");
  });

  it("draws inline code as a tinted pill with padded ends", async () => {
    const view = await render(<MarkdownContent content={'Set `name = "john"` then continue.'} />);
    const snippet = view.getByText('name = "john"');
    expect(StyleSheet.flatten(snippet.props.style)).toMatchObject({
      backgroundColor: lightTheme.codeInlineBg,
      fontFamily: CODE_FONT,
      fontSize: Type.secondary.fontSize,
      color: lightTheme.text,
    });
    // Nested Text takes no padding: a no-break space pads each end.
    const kids = snippet.props.children as unknown[];
    expect(strings(view.toJSON() as Node)).toContain(' name = "john" ');
    expect(kids).toHaveLength(3);
  });

  it("keeps the pill in bold, headings, list items and table cells", async () => {
    const content = [
      "### Call `print()` once",
      "",
      "**Run `total += n`** now.",
      "",
      "- `IndexError` is raised",
      "",
      "| Name | Code |",
      "| --- | --- |",
      "| sum | `total` |",
    ].join("\n");
    const view = await render(<MarkdownContent content={content} />);
    const style = (label: string) => StyleSheet.flatten(view.getByText(label).props.style);
    for (const label of ["print()", "total += n", "IndexError", "total"]) {
      expect({ label, ...style(label) }).toMatchObject({
        label,
        backgroundColor: lightTheme.codeInlineBg,
        fontFamily: CODE_FONT,
      });
    }
    // Heading code keeps the body's 14:16 ratio; table code the cell's size.
    expect(style("print()").fontSize).toBe(
      Math.round((Type.h3.fontSize * Type.secondary.fontSize) / Type.body.fontSize),
    );
    expect(style("total").fontSize).toBe(Type.compact.fontSize);
  });

  it("uses the dark pill in dark mode", () => {
    expect(inlineCodeTextStyle(darkTheme)).toMatchObject({
      backgroundColor: darkTheme.codeInlineBg,
      color: darkTheme.text,
    });
  });
});

describe("a line-by-line lesson", () => {
  const LESSON = [
    "### 1. The code",
    "",
    "```python",
    "total = 0",
    "```",
    "",
    "### 2. Explain each line",
    "",
    "**Line 1:** `total = 0`",
    "Creates a variable `total` and sets it to `0`.",
  ].join("\n");

  it("renders numbered ### headings as section titles", async () => {
    const view = await render(<MarkdownContent content={LESSON} />);
    for (const title of ["1. The code", "2. Explain each line"]) {
      expect(StyleSheet.flatten(view.getByText(title).props.style)).toMatchObject({
        fontSize: Type.h3.fontSize,
        fontFamily: Type.h3.fontFamily,
      });
    }
  });

  it("keeps a bold label and its code on one row, the explanation under it", async () => {
    const view = await render(<MarkdownContent content={LESSON} />);
    // The label, a space and the pill share one wrapping Text run.
    expect(view.getByText("Line 1: total = 0")).toBeOnTheScreen();
    expect(view.getByText("Line 1:")).toBeOnTheScreen();
    const explanation = view.getByText(/^Creates a variable/);
    expect(strings(explanation as unknown as Node)).not.toContain("Line 1");
  });
});

describe("inline code in rich cards", () => {
  it("draws a quiz option's code as the same pill", async () => {
    const view = await render(
      <ChipText style={{}} chip={inlineCodeTextStyle(lightTheme)}>
        {"Use `numbers[2]` here"}
      </ChipText>,
    );
    expect(StyleSheet.flatten(view.getByText("numbers[2]").props.style)).toMatchObject({
      backgroundColor: lightTheme.codeInlineBg,
      fontFamily: CODE_FONT,
    });
  });

  it("keeps a callout's code span as one pill beside maths", async () => {
    const view = await render(
      <RichMathBody content={"Set `total = total + n` so $x = 2$"} />,
    );
    expect(StyleSheet.flatten(view.getByText("total = total + n").props.style)).toMatchObject({
      backgroundColor: lightTheme.codeInlineBg,
      fontFamily: CODE_FONT,
    });
  });
});
