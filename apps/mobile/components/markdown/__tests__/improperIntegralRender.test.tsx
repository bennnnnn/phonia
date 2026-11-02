import { render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { IMPROPER_RESPONSE } from "../../../lib/__tests__/fixtures/improperIntegralResponse";

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

type RenderNode = string | { children?: RenderNode[] | null } | RenderNode[] | null;
function visibleText(node: RenderNode): string {
  if (node == null) return "";
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(visibleText).join("");
  return (node.children ?? []).map(visibleText).join("");
}

describe("improper integral absolute-value rendering", () => {
  it.each([false, true])("preserves native math bars and nested list structure, streaming=%s", async (streaming) => {
    const { toJSON, queryByText } = await render(<MarkdownContent content={IMPROPER_RESPONSE} streaming={streaming} />);
    const visible = visibleText(toJSON());
    const compact = visible.replace(/\s+/g, "");
    expect(compact).toContain("ln|a|−ln|−1|");
    expect(compact).toContain("ln|1|−ln|b|");
    expect(compact).not.toContain("lnor");
    expect(visible).not.toContain("| ---");
    expect(queryByText(/\\ln|\\lim|\$/)).toBeNull();
  });
});
