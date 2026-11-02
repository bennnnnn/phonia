import { StyleSheet, type StyleProp, type TextStyle } from "react-native";
import { render, type RenderResult } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { withStreamCaret, STREAM_CARET } from "@/components/StreamingCursor";

jest.mock("@/components/LinkPreviewCard", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    LinkPreviewCard: ({ url }: { url: string }) => <Text>{url}</Text>,
  };
});

function graySlabs(view: RenderResult): unknown[] {
  const found: unknown[] = [];
  const walk = (node: unknown) => {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    const record = node as { props?: { style?: StyleProp<TextStyle> }; children?: unknown };
    const flat = StyleSheet.flatten(record.props?.style);
    if (
      flat?.width === "100%" &&
      (flat.height === 32 || flat.height === 48 || flat.height === 96)
    ) {
      found.push(node);
    }
    walk(record.children);
  };
  walk(view.toJSON());
  return found;
}

describe("streaming caret", () => {
  it("keeps the caret mark on the last prose line", () => {
    expect(withStreamCaret("Hello\n")).toBe(`Hello${STREAM_CARET}\n`);
    expect(withStreamCaret("Hello")).toBe(`Hello${STREAM_CARET}`);
  });

  it("puts the caret on the prose line and does not paint a bar for an open fraction", async () => {
    const view = await render(
      <MarkdownContent content={"The answer is $\\frac{1"} streaming />,
    );
    expect(graySlabs(view)).toHaveLength(0);
    expect(view.getByText(/The answer is/)).toBeOnTheScreen();
    expect(view.queryByText(/\\frac/)).toBeNull();
    const caret = view.getByTestId("stream-caret", { includeHiddenElements: true });
    expect(caret.type).toBe("Text");
    expect(caret.parent?.type).toBe("Text");
  });

  it("draws a closed display prefix instead of a gray slab", async () => {
    const view = await render(
      <MarkdownContent content={"\\[\n\\frac{1}{2} + \\frac{3"} streaming />,
    );
    expect(graySlabs(view)).toHaveLength(0);
    expect(view.getByText("1")).toBeOnTheScreen();
    expect(view.getByText("2")).toBeOnTheScreen();
    expect(view.getByTestId("stream-caret", { includeHiddenElements: true })).toBeTruthy();
  });

  it("draws the caret, never its mark, after a worked section's last line", async () => {
    const view = await render(
      <MarkdownContent content={"**Given**  \n$m = 0.2\\,\\mathrm{kg}$  \n$v_1 = 10"} streaming />,
    );
    expect(JSON.stringify(view.toJSON())).not.toContain(STREAM_CARET);
    expect(view.getByTestId("workout-section")).toBeOnTheScreen();
    expect(view.getByTestId("stream-caret", { includeHiddenElements: true })).toBeTruthy();
  });

  it("keeps an open code fence as a code card", async () => {
    const view = await render(
      <MarkdownContent content={"```python\nprint(1)\n"} streaming />,
    );
    expect(view.getByText(/print\(1\)/)).toBeOnTheScreen();
    expect(graySlabs(view)).toHaveLength(0);
    expect(view.getByTestId("stream-caret", { includeHiddenElements: true })).toBeTruthy();
  });

  it("does not paint a gray block for an open geometry fence", async () => {
    const view = await render(
      <MarkdownContent content={'A triangle.\n```geometry\n{"type":"segment"\n'} streaming />,
    );
    expect(graySlabs(view)).toHaveLength(0);
    expect(view.queryByText(/segment/)).toBeNull();
    const caret = view.getByTestId("stream-caret", { includeHiddenElements: true });
    expect(view.getByText(/A triangle/)).toBeOnTheScreen();
    expect(caret.type).toBe("Text");
    expect(caret.parent?.type).toBe("Text");
  });
});
