/**
 * A heavy answer is drawn by MathSvgView: its latex grows while the answer
 * fence streams, and the server may replace the value at `done`. The card
 * keeps its view through both, so it must always draw its own latex, never a
 * conversion made for the latex it had before.
 */
import { act, render, waitFor } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { formatAssistantMathExpr } from "@/lib/math/formatInput";
import { setSvgMathRendererForTest } from "@/lib/math/svgMath";

const mockDrawn = jest.fn((_props: { xml: string }) => null);
jest.mock("react-native-svg", () => {
  const actual = jest.requireActual("react-native-svg");
  return {
    ...actual,
    parse: (xml: string) => ({ xml }),
    SvgAst: ({ ast }: { ast: { xml: string } }) => mockDrawn({ xml: ast.xml }),
  };
});
jest.mock("@/ui/icons/Icon", () => {
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  return { Icon: ({ testID }: { testID?: string }) => <View testID={testID} /> };
});
jest.mock("@/components/LinkPreviewCard", () => ({ LinkPreviewCard: "LinkPreviewCard" }));

beforeEach(() => {
  // Each formula's SVG names the formula it was made from.
  setSvgMathRendererForTest(
    (latex: string) =>
      `<mjx-container><svg xmlns="http://www.w3.org/2000/svg" width="2ex" height="1ex" viewBox="0 0 800 500"><path data-formula="${latex.replace(/[\\{}&"]/g, "")}" fill="currentColor" d="M0 0"></path></svg></mjx-container>`,
  );
});
afterEach(() => {
  setSvgMathRendererForTest(null);
  mockDrawn.mockClear();
});

const FENCE = "```";
const drawnFormula = () => /data-formula="([^"]*)"/.exec(mockDrawn.mock.calls.at(-1)?.[0].xml ?? "")?.[1];

async function stream(text: string, step: number) {
  const view = await render(<MarkdownContent content="" streaming mathFormat={formatAssistantMathExpr} />);
  for (let end = step; end < text.length + step; end += step) {
    const content = text.slice(0, Math.min(end, text.length));
    await act(async () => {
      view.rerender(<MarkdownContent content={content} streaming mathFormat={formatAssistantMathExpr} />);
    });
    // The conversion resolves between flushes, as it does ~33 ms apart on the phone.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
  return view;
}

async function settle(view: Awaited<ReturnType<typeof stream>>, text: string) {
  await act(async () => {
    view.rerender(<MarkdownContent content={text} mathFormat={formatAssistantMathExpr} />);
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

describe("a heavy answer card", () => {
  const reply = `We integrate term by term.\n\n**Answer**\n\n${FENCE}answer\n\\int_0^1 x^2\\,dx = \\frac{1}{3}\n${FENCE}\n\nThat is the area.\n`;

  it.each([3, 7, 12])("streamed %i characters a flush draws its whole value", async (step) => {
    const view = await stream(reply, step);
    await settle(view, reply);
    expect(drawnFormula()).toBe("int_0^1 x^2,dx = frac13");
    await view.unmount();

    // Drawn again later (the chat reopened): the same, not a partial value.
    mockDrawn.mockClear();
    const reopened = await render(<MarkdownContent content={reply} mathFormat={formatAssistantMathExpr} />);
    await waitFor(() => expect(drawnFormula()).toBe("int_0^1 x^2,dx = frac13"));
    await reopened.unmount();
  });

  it("draws the server's verified value when it replaces the streamed one at `done`", async () => {
    const intro = "We count the ways to pick two of five.\n\n**Answer**\n\n";
    const streamed = `${intro}${FENCE}answer\n\\binom{5}{2} = 12\n${FENCE}\n\nThat is the count.\n`;
    const saved = `${intro}${FENCE}answer\nverified: true\n\\binom{5}{2} = 10\n${FENCE}\n\nThat is the count.\n`;
    const view = await stream(streamed, 20);
    await waitFor(() => expect(drawnFormula()).toBe("binom52 = 12"));

    await settle(view, saved);
    expect(drawnFormula()).toBe("binom52 = 10");
    expect(view.getByTestId("answer-success-check")).toBeTruthy();
    await view.unmount();

    mockDrawn.mockClear();
    const reopened = await render(<MarkdownContent content={saved} mathFormat={formatAssistantMathExpr} />);
    await waitFor(() => expect(drawnFormula()).toBe("binom52 = 10"));
    await reopened.unmount();
  });
});
