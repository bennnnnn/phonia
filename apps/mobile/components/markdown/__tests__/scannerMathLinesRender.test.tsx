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
jest.mock("react-native-webview", () => {
  throw new Error("react-native-webview native module is not linked (test)");
});
jest.mock("@expo/dom-webview", () => {
  throw new Error("@expo/dom-webview native module is not linked (test)");
});
jest.mock("@/components/CodeBlock", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    CodeBlock: ({ code, lang }: { code: string; lang: string }) => (
      <RNText>{`${lang}:${code}`}</RNText>
    ),
  };
});

const SCANNER_RESPONSE = "Here's how to solve for $x$ step-by-step:\n\n1.  **Original Equation:** `$2x + 3 = 5$`\n2.  **Subtract 3 from both sides:** To isolate the term with $x$, subtract 3 from both sides of the equation.\n    `$2x + 3 - 3 = 5 - 3$`\n    `$2x = 2$`\n3.  **Divide by 2:** To solve for $x$, divide both sides by 2.\n    `$\\frac{2x}{2} = \\frac{2}{2}$`\n    `$x = 1$`\n\nSo, the solution is $x = 1$.";
type RenderNode = string | { children?: RenderNode[] | null } | RenderNode[] | null;
function visibleText(node: RenderNode): string {
  if (node == null) return "";
  // A formula's spaces are no-break spaces; on screen they read as spaces.
  if (typeof node === "string") return node.replace(/\u00a0/g, " ");
  if (Array.isArray(node)) return node.map(visibleText).join("");
  return (node.children ?? []).map(visibleText).join("");
}

describe("scanner calculation lines", () => {
  it.each([false, true])("renders actual scanner steps on separate native lines, streaming=%s", async (streaming) => {
    const { toJSON, queryByText } = await render(<MarkdownContent content={SCANNER_RESPONSE} streaming={streaming} />);
    expect(visibleText(toJSON())).toContain("2x + 3 − 3 = 5 − 3\n2x = 2");
    expect(visibleText(toJSON())).toContain("\nx = 1");
    expect(queryByText(/`|\\frac|\$/)).toBeNull();
  });
});
