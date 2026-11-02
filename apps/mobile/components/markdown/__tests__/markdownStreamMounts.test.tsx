/**
 * A flush updates the reply's live part in place: what was already drawn keeps
 * its views (react-native-markdown-display re-keys every node on each parse;
 * withStableNodeKeys keys them by their place instead), a chunk cut from the
 * live part keeps them too, and so does the reply when it settles.
 */
import { act, render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";

const mockMounts = new Map<string, number>();

jest.mock("@/components/LinkPreviewCard", () => ({ LinkPreviewCard: "LinkPreviewCard" }));

jest.mock("@/components/rich/MathText", () => {
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  const { useEffect: useMountEffect } = jest.requireActual<typeof import("react")>("react");
  return {
    MathText: ({ latex }: { latex: string }) => {
      useMountEffect(() => {
        mockMounts.set(latex, (mockMounts.get(latex) ?? 0) + 1);
      }, []);
      return <Text>{latex}</Text>;
    },
  };
});

const PARAGRAPH = "Each step keeps the value: " + "and the next word follows ".repeat(10);

/** Stream `lines`, each in two flushes unless `wholeLines`. */
async function streamLines(lines: string[], wholeLines = false) {
  const view = await render(<MarkdownContent content="" streaming />);
  let text = "";
  for (const line of lines) {
    text += `${line}\n`;
    const cuts = wholeLines ? [text.length] : [text.length - line.length / 2, text.length];
    for (const cut of cuts) {
      const content = text.slice(0, Math.floor(cut));
      await act(async () => {
        view.rerender(<MarkdownContent content={content} streaming />);
      });
    }
  }
  return view;
}

beforeEach(() => mockMounts.clear());

describe("a streaming reply's live part", () => {
  it("keeps the formulas it drew while it grows", async () => {
    const lines = ["Intro with $a^2$ in it.", "", "- First $b+1$ item", "- Second $b+2$ item", "- Third item"];
    const view = await streamLines(lines);
    expect(Object.fromEntries(mockMounts)).toEqual({ "a^2": 1, "b+1": 1, "b+2": 1 });
    await view.unmount();
  });

  it("keeps them when the live part is cut into a chunk", async () => {
    const lines = [`First $c^2$ ${PARAGRAPH}`, "", `Second ${PARAGRAPH}`, "", `Third ${PARAGRAPH}`, ""];
    const view = await streamLines(lines, true);
    // Two pieces: the chunk holding the first two paragraphs, then the live one.
    const root = view.toJSON() as { children: { props: { testID?: string } }[] };
    expect(root.children.filter((piece) => piece.props.testID === undefined)).toHaveLength(2);
    expect(mockMounts.get("c^2")).toBe(1);
    await view.unmount();
  });
});

describe("a streamed reply that settles", () => {
  it("keeps every view it drew, and only its answer gains the check", async () => {
    const lines = [
      `First $c^2$ ${PARAGRAPH}`,
      "",
      `Second $d^2$ ${PARAGRAPH}`,
      "",
      "```answer",
      "verified: true",
      "$x = 4$",
      "```",
      "",
      "Third $e^2$ and the rest",
    ];
    const view = await streamLines(lines);
    expect(view.queryByTestId("answer-success-check")).toBeNull();
    const caretBefore = view.queryAllByTestId("stream-caret", { includeHiddenElements: true }).length;
    const answerBox = view.getByTestId("answer-box");
    const mountedWhileStreaming = Object.fromEntries(mockMounts);
    expect(mountedWhileStreaming).toEqual(expect.objectContaining({ "c^2": 1, "d^2": 1, "x = 4": 1 }));

    await act(async () => {
      view.rerender(<MarkdownContent content={`${lines.join("\n")}\n`} />);
    });
    // Settling mounts nothing: every formula is the one drawn while it streamed.
    expect(Object.fromEntries(mockMounts)).toEqual(mountedWhileStreaming);
    expect(view.getByTestId("answer-box")).toBe(answerBox);
    expect(view.getByTestId("answer-success-check")).toBeTruthy();
    expect(caretBefore).toBeGreaterThan(0);
    expect(view.queryAllByTestId("stream-caret", { includeHiddenElements: true })).toHaveLength(0);
    await view.unmount();
  });
});
