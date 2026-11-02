import { render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";

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
jest.mock("@/components/rich/MathText", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    MathText: ({ latex }: { latex: string }) => <RNText>{`MATH:${latex}`}</RNText>,
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

function outermostTextAncestor(node: { type?: string; parent?: unknown }) {
  let cur = node.parent as typeof node | undefined;
  let last: typeof node | null = null;
  while (cur) {
    if (cur.type === "Text") {
      last = cur;
      cur = cur.parent as typeof node | undefined;
      continue;
    }
    break;
  }
  return last;
}

function ownText(node: { children: unknown[] }): string {
  return node.children.filter((child): child is string => typeof child === "string").join("");
}

function visibleText(node: { children: unknown[] }): string {
  return node.children
    .map((child) => (typeof child === "string" ? child : visibleText(child as { children: unknown[] })))
    .join("");
}

function paragraphText(node: { type?: string; parent?: unknown; children: unknown[] }) {
  let current = node;
  let parent = current.parent as typeof current | undefined;
  while (parent?.type === "Text") {
    current = parent;
    parent = current.parent as typeof current | undefined;
  }
  return current;
}

describe("markdown token boundaries", () => {
  it("keeps prose, bold values, and trailing prose on one inline run", async () => {
    const { getByText } = await render(
      <MarkdownContent content="A train travels at**60 km/h** and returns at**40 km/h**." />,
    );
    const speed = getByText("40 km/h");
    const paragraph = paragraphText(speed);
    const pieces = paragraph.children.filter(
      (child): child is { type?: string; parent?: unknown; children: unknown[] } =>
        typeof child === "object" && child !== null,
    );
    const before = pieces.find((piece) => ownText(piece).endsWith("at "));
    expect(before).toBeTruthy();
    expect(ownText(before!)).toMatch(/at $/);
    expect(getByText("60 km/h")).toBeTruthy();
    expect(outermostTextAncestor(before!)).toBe(outermostTextAncestor(speed));
    expect(visibleText(paragraph)).toBe("A train travels at 60 km/h and returns at 40 km/h.");
  });

  it("keeps a cyclist sentence from gluing the next value", async () => {
    const { getByText } = await render(
      <MarkdownContent content="A cyclist rides **12 km** at**20 km/h**, then**8 km** at**10 km/h**." />,
    );
    const speed = getByText("20 km/h");
    expect(visibleText(paragraphText(speed))).toBe(
      "A cyclist rides 12 km at 20 km/h, then 8 km at 10 km/h.",
    );
    expect(getByText("8 km")).toBeTruthy();
    expect(getByText("10 km/h")).toBeTruthy();
  });

  it("renders one math row per reasoning state and keeps a wide formula whole", async () => {
    const chain = await render(<MarkdownContent content="$v = d/t = 50/10 = 5$" />);
    expect(chain.getByText("MATH:v = d/t")).toBeTruthy();
    expect(chain.getByText("MATH:v = 50/10")).toBeTruthy();
    expect(chain.getByText("MATH:v = 5")).toBeTruthy();

    const quadratic = "$x = \\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}$";
    const wide = await render(<MarkdownContent content={quadratic} />);
    expect(wide.getByText("MATH:x = \\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}")).toBeTruthy();
  });

  it("still renders a list, a quote, and a code fence", async () => {
    const { getByText } = await render(
      <MarkdownContent
        content={"- Use `yield` carefully.\n\n> A short quote.\n\n```python\nprint(1)\n```"}
      />,
    );
    expect(getByText("yield")).toBeTruthy();
    expect(getByText(/A short quote/)).toBeTruthy();
    expect(getByText("python:print(1)")).toBeTruthy();
  });
});
