/**
 * A flush of a streaming reply costs the text that arrived, not the reply so
 * far: the characters handed to `preprocessMarkdown` and to the markdown
 * parser in a flush stay level as the reply grows, the markdown renderer is
 * built when a piece mounts, not on every flush, and what is already drawn (a
 * closed fence, a table's finished rows, a list's finished items) is not drawn
 * again while the text after it streams. Counted, never timed.
 */
import { act, render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { STREAMING_REPLIES } from "@/lib/__tests__/fixtures/streamingReplies";
import * as preprocess from "@/lib/markdown/preprocess";
import { formatAssistantMathExpr } from "@/lib/math/formatInput";

const mockWork = { preprocessed: 0, parsed: 0, renderers: 0, mounts: 0, codeBlocks: 0, cells: 0, codeSpans: 0 };

jest.mock("@/components/LinkPreviewCard", () => ({ LinkPreviewCard: "LinkPreviewCard" }));
jest.mock("react-native-markdown-display", () => {
  const actual = jest.requireActual("react-native-markdown-display");
  const { useEffect: useMountEffect } = jest.requireActual<typeof import("react")>("react");
  const Markdown = actual.default;
  function CountedMarkdown(props: { children: string }) {
    mockWork.parsed += props.children.length;
    useMountEffect(() => {
      mockWork.mounts += 1;
    }, []);
    return <Markdown {...props} />;
  }
  return { ...actual, __esModule: true, default: CountedMarkdown };
});

// Each renderer the markdown library builds: every style flattened, the rules merged.
jest.mock("react-native-markdown-display/src/lib/AstRenderer", () => {
  const Actual = jest.requireActual("react-native-markdown-display/src/lib/AstRenderer").default;
  class CountedRenderer extends Actual {
    constructor(...args: unknown[]) {
      super(...args);
      mockWork.renderers += 1;
    }
  }
  return { __esModule: true, default: CountedRenderer };
});

jest.mock("@/components/CodeBlock", () => {
  const actual = jest.requireActual<typeof import("@/components/CodeBlock")>("@/components/CodeBlock");
  function CountedCodeBlock(props: Parameters<typeof actual.CodeBlock>[0]) {
    mockWork.codeBlocks += 1;
    return actual.CodeBlock(props);
  }
  return { ...actual, CodeBlock: CountedCodeBlock };
});

jest.mock("@/components/MarkdownTable", () => {
  const actual = jest.requireActual<typeof import("@/components/MarkdownTable")>("@/components/MarkdownTable");
  function CountedCell(props: Parameters<typeof actual.MarkdownTableCell>[0]) {
    mockWork.cells += 1;
    return actual.MarkdownTableCell(props);
  }
  return { ...actual, MarkdownTableCell: CountedCell };
});

jest.mock("@/components/markdown/InlineCode", () => {
  const actual = jest.requireActual<typeof import("@/components/markdown/InlineCode")>(
    "@/components/markdown/InlineCode",
  );
  function CountedInlineCode(props: Parameters<typeof actual.InlineCode>[0]) {
    mockWork.codeSpans += 1;
    return actual.InlineCode(props);
  }
  return { ...actual, InlineCode: CountedInlineCode };
});

const realPreprocess = preprocess.preprocessMarkdown;
jest.spyOn(preprocess, "preprocessMarkdown").mockImplementation((text, ...rest) => {
  mockWork.preprocessed += text.length;
  return realPreprocess(text, ...rest);
});

/** The fixture replies one after another: a reply several times the usual length. */
const LONG_REPLY = [
  STREAMING_REPLIES.maths,
  STREAMING_REPLIES.tips,
  STREAMING_REPLIES.mixed,
  STREAMING_REPLIES.maths,
  STREAMING_REPLIES.nested,
  STREAMING_REPLIES.maths,
].join("\n\n");

type Flush = { at: number; preprocessed: number; parsed: number; renderers: number; mounts: number };

async function streamCounting(text: string, step = 24): Promise<Flush[]> {
  const view = await render(
    <MarkdownContent content="" streaming mathFormat={formatAssistantMathExpr} />,
  );
  const flushes: Flush[] = [];
  for (let end = step; end < text.length + step; end += step) {
    const at = Math.min(end, text.length);
    mockWork.preprocessed = 0;
    mockWork.parsed = 0;
    mockWork.renderers = 0;
    mockWork.mounts = 0;
    await act(async () => {
      view.rerender(
        <MarkdownContent content={text.slice(0, at)} streaming mathFormat={formatAssistantMathExpr} />,
      );
    });
    flushes.push({ at, ...mockWork });
  }
  await view.unmount();
  return flushes;
}

function mean(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

describe("a streaming reply's work per flush", () => {
  it("stays level from the start of a long reply to its end", async () => {
    const flushes = await streamCounting(LONG_REPLY);
    expect(LONG_REPLY.length).toBeGreaterThan(10_000);
    const early = flushes.filter((flush) => flush.at > 1_000 && flush.at <= 4_000);
    const late = flushes.filter((flush) => flush.at > LONG_REPLY.length - 3_000);

    for (const kind of ["preprocessed", "parsed"] as const) {
      // Late in the reply a flush does about what it did early on…
      expect(mean(late.map((flush) => flush[kind]))).toBeLessThan(
        2 * mean(early.map((flush) => flush[kind])) + 200,
      );
      // …and no flush comes near the reply's whole length.
      expect(Math.max(...late.map((flush) => flush[kind]))).toBeLessThan(LONG_REPLY.length / 4);
    }
  }, 300_000);

  it("builds the markdown renderer when a piece mounts, not on every flush", async () => {
    // The live piece re-renders on every flush; a renderer built each time
    // flattened every style again (487 builds over this reply's 484 flushes).
    const flushes = await streamCounting(LONG_REPLY);
    const total = (kind: "renderers" | "mounts") =>
      flushes.reduce((sum, flush) => sum + flush[kind], 0);
    // A piece drawn as a list that goes on swaps its rules once: a build too.
    expect(total("renderers")).toBeLessThanOrEqual(2 * total("mounts"));
    expect(total("renderers")).toBeLessThan(flushes.length / 4);
  }, 300_000);

  it("leaves a closed fence as it was drawn while the text after it streams", async () => {
    const fence = ["```python", ...Array.from({ length: 20 }, (_, i) => `total += step(${i})`), "```"];
    const before = `Here is the loop.\n\n${fence.join("\n")}\n\n`;
    // The last line stays open, so the fence stays in the live piece under it.
    const after = "It runs once per step and keeps the running total, ".repeat(8);
    const view = await render(<MarkdownContent content={before} streaming />);
    let drawn = 0;
    for (let end = 24; end <= after.length; end += 24) {
      mockWork.codeBlocks = 0;
      await act(async () => {
        view.rerender(<MarkdownContent content={before + after.slice(0, end)} streaming />);
      });
      drawn += mockWork.codeBlocks;
    }
    // Each of the 17 flushes went through the code card again (0.9 ms each in jest).
    expect(drawn).toBe(0);
    await view.unmount();
  });

  it("settles without preprocessing the whole reply again", async () => {
    const text = LONG_REPLY.trim();
    const view = await render(<MarkdownContent content="" streaming mathFormat={formatAssistantMathExpr} />);
    for (let end = 24; end < text.length + 24; end += 24) {
      await act(async () => {
        view.rerender(
          <MarkdownContent content={text.slice(0, end)} streaming mathFormat={formatAssistantMathExpr} />,
        );
      });
    }
    mockWork.preprocessed = 0;
    await act(async () => {
      view.rerender(<MarkdownContent content={text} mathFormat={formatAssistantMathExpr} />);
    });
    // The settled reply was preprocessed whole again: all 11,610 characters.
    expect(mockWork.preprocessed).toBeLessThan(text.length / 10);
    expect(mockWork.preprocessed).toBeGreaterThan(0);
    await view.unmount();
  }, 300_000);

  it("redraws only the list item still being written", async () => {
    // A numbered list is not cut before item 11, so it stays in the live piece.
    const items = Array.from(
      { length: 10 },
      (_, i) => `${i + 1}. **Step ${i + 1}** – run \`step_${i + 1}()\` and check what it returns before you go on.`,
    );
    const list = `Here is the plan.\n\n${items.join("\n")}\n`;
    const view = await render(<MarkdownContent content="" streaming />);
    const perFlush: number[] = [];
    for (let end = 16; end <= list.length; end += 16) {
      mockWork.codeSpans = 0;
      await act(async () => {
        view.rerender(<MarkdownContent content={list.slice(0, end)} streaming />);
      });
      perFlush.push(mockWork.codeSpans);
    }
    // Every flush drew every item's code span again (8 to 10 a flush over the last
    // ten). Now one flush does: item 10 widens the number column of every item.
    expect(perFlush.slice(-10).filter((spans) => spans > 2)).toHaveLength(1);
    await view.unmount();
  });

  it("redraws only the table row still being written", async () => {
    const rows = Array.from({ length: 16 }, (_, i) => `| Plan ${i + 1} | ${i + 1} GB | Email |`);
    const table = ["| Plan | Storage | Support |", "| --- | --- | --- |", ...rows].join("\n");
    const view = await render(<MarkdownContent content="" streaming />);
    const perFlush: number[] = [];
    for (let end = 16; end <= table.length; end += 16) {
      mockWork.cells = 0;
      await act(async () => {
        view.rerender(<MarkdownContent content={table.slice(0, end)} streaming />);
      });
      perFlush.push(mockWork.cells);
    }
    // Every flush drew every cell again (33 to 48 a flush over the last ten);
    // now the row being written, and the one before it as it stops being last.
    expect(Math.max(...perFlush.slice(-10))).toBeLessThanOrEqual(6);
    await view.unmount();
  });
});
