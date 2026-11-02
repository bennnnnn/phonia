import { render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { AnswerBlock } from "@/components/rich/AnswerBlock";

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

const C14_RESPONSE = "The Taylor series of \\( f(x) = e^x \\) centered at \\( a = 1 \\), up to order 2, is:\n\n\\[\nf(x) \\approx f(1) + f'(1)(x-1) + \\frac{f''(1)}{2}(x-1)^2\n\\]\n\n**Terms calculated:**  \n1. \\( f(1) = e^1 = e \\)  \n2. \\( f'(x) = e^x \\) \u2192 \\( f'(1) = e \\)  \n3. \\( f''(x) = e^x \\) \u2192 \\( f''(1) = e \\)  \n\n**Result:**  \n\\[\ne^x \\approx e + e(x-1) + \\frac{e}{2}(x-1)^2 + \\cdots\n\\]\n\n---\n\n### Explanation:\n- **Taylor series** approximates a function near a point \\( a \\) using the function\u2019s derivatives at \\( a \\).  \n- For \\( e^x \\), all derivatives are \\( e^x \\), simplifying calculations.  \n- Higher-order terms (e.g., \\( (x-1)^3 \\)) are truncated at order 2.";

describe("native derivative and function notation", () => {
  it.each([false, true])("renders C14 primes without Markdown quotation marks, streaming=%s", async (streaming) => {
    const { getAllByText, queryByText } = await render(<MarkdownContent content={C14_RESPONSE} streaming={streaming} />);
    expect(getAllByText(/f′\(x\)/).length).toBeGreaterThan(0);
    expect(getAllByText(/f′′\(x\)/).length).toBeGreaterThan(0);
    expect(queryByText(/f[‘’]|[\uE000-\uE005]/)).toBeNull();
  });
  it("renders the exact C18 standalone answer with ordinary function arguments", async () => {
    const { getByText, getAllByTestId, queryByText } = await render(
      <AnswerBlock content={String.raw`y{\left(x \right)} = C_{1} + x^{2}`} />,
    );
    expect(getByText("y(x) = C")).toBeOnTheScreen();
    expect(getAllByTestId("math-script").map((node) => [].concat(node.props.children).join(""))).toEqual(["1", "2"]);
    expect(queryByText("₁")).toBeNull();
    expect(queryByText("²")).toBeNull();
    expect(queryByText(/[{}]/)).toBeNull();
  });
});
