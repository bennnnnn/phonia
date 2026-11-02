/**
 * A streaming reply is drawn in pieces: settled chunks that each parse once,
 * then the live part (MarkdownContent, lib/markdown/streamBlocks.ts). A chunk
 * may end between two items of a list, drawn as a list that goes on. At every
 * line of the stream, the pieces must look exactly like the whole stable text
 * drawn as one piece.
 */
import { act, render } from "@testing-library/react-native";
import { StyleSheet, type StyleProp, type TextStyle } from "react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { STREAMING_REPLIES } from "@/lib/__tests__/fixtures/streamingReplies";
import { advanceStreamBlocks } from "@/lib/markdown/streamBlocks";
import { formatAssistantMathExpr } from "@/lib/math/formatInput";

import physics from "../../../../../docs/fixtures/physics_replies.json";

jest.mock("@/components/LinkPreviewCard", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return { LinkPreviewCard: ({ url }: { url: string }) => <Text>{url}</Text> };
});

/** While set, the reply is not chunked: the stable text is one piece. */
let mockOnePiece = false;
jest.mock("@/lib/markdown/streamBlocks", () => {
  const actual = jest.requireActual<typeof import("@/lib/markdown/streamBlocks")>(
    "@/lib/markdown/streamBlocks",
  );
  return {
    ...actual,
    advanceStreamBlocks: (...args: Parameters<typeof actual.advanceStreamBlocks>) =>
      mockOnePiece ? actual.emptyStreamBlocksState() : actual.advanceStreamBlocks(...args),
  };
});

type Json = { type: string; props: Record<string, unknown>; children: (Json | string)[] | null };
type Drawn = Json | string;

/** Props as drawn: styles flattened, callbacks and the caret's blink phase left out. */
function drawn(node: Drawn, inCaret = false): Drawn {
  if (typeof node === "string") return node;
  const caret = inCaret || node.props.testID === "stream-caret";
  const props: Record<string, unknown> = {};
  for (const [name, value] of Object.entries(node.props)) {
    if (typeof value === "function") continue;
    if (name !== "style") {
      props[name] = value;
      continue;
    }
    const style = { ...StyleSheet.flatten(value as StyleProp<TextStyle>) } as Record<string, unknown>;
    if (caret) delete style.opacity;
    props.style = style;
  }
  return { type: node.type, props, children: (node.children ?? []).map((child) => drawn(child, caret)) };
}

const LIST_IDS = new Set(["md-bullet-list", "md-ordered-list"]);

function isList(node: Drawn | undefined): node is Json {
  return typeof node === "object" && LIST_IDS.has(String(node.props.testID));
}

/** A piece's body: the plain View every `Markdown` wraps its blocks in. */
function isPieceBody(node: Drawn): node is Json {
  return (
    typeof node === "object" &&
    node.type === "View" &&
    node.props.testID === undefined &&
    Object.keys(node.props.style as object).length === 0
  );
}

/** The blocks of a reply, in order: pieces unwrapped, and a list that goes on joined to the rest of it. */
function blocksOf(tree: Json): Drawn[] {
  const root = drawn(tree) as Json;
  const blocks: Drawn[] = [];
  for (const child of root.children ?? []) {
    for (const block of isPieceBody(child) ? (child.children ?? []) : [child]) {
      const previous = blocks[blocks.length - 1];
      const goesOn =
        isList(previous) &&
        isList(block) &&
        previous.props.testID === block.props.testID &&
        (previous.props.style as { marginBottom?: number }).marginBottom === 0;
      if (goesOn) {
        blocks[blocks.length - 1] = {
          ...block,
          children: [...(previous.children ?? []), ...(block.children ?? [])],
        };
      } else {
        blocks.push(block);
      }
    }
  }
  return blocks;
}

function lineEnds(text: string): number[] {
  const ends: number[] = [];
  for (let i = text.indexOf("\n"); i >= 0; i = text.indexOf("\n", i + 1)) ends.push(i + 1);
  ends.push(text.length);
  return ends;
}

async function drawnInOnePiece(content: string): Promise<Drawn[]> {
  mockOnePiece = true;
  try {
    const view = await render(
      <MarkdownContent content={content} streaming mathFormat={formatAssistantMathExpr} />,
    );
    const blocks = blocksOf(view.toJSON() as Json);
    await view.unmount();
    return blocks;
  } finally {
    mockOnePiece = false;
  }
}

const replies = Object.entries({
  ...STREAMING_REPLIES,
  projectile: physics.replies.projectile_parts.reply,
});

describe("a streaming reply drawn in pieces", () => {
  it.each(replies)(
    "%s looks the same as one piece at every line",
    async (_name, text) => {
      const live = await render(
        <MarkdownContent content="" streaming mathFormat={formatAssistantMathExpr} />,
      );
      const differ: number[] = [];
      for (const end of lineEnds(text)) {
        const content = text.slice(0, end);
        await act(async () => {
          live.rerender(
            <MarkdownContent content={content} streaming mathFormat={formatAssistantMathExpr} />,
          );
        });
        const pieces = JSON.stringify(blocksOf(live.toJSON() as Json));
        if (pieces !== JSON.stringify(await drawnInOnePiece(content))) differ.push(end);
      }
      await live.unmount();
      expect(differ).toEqual([]);
    },
    120_000,
  );

  it("draws a long list in several pieces", async () => {
    const view = await render(
      <MarkdownContent content={STREAMING_REPLIES.tips} streaming mathFormat={formatAssistantMathExpr} />,
    );
    const goesOn = view
      .getAllByTestId("md-bullet-list")
      .filter((list) => StyleSheet.flatten(list.props.style)?.marginBottom === 0);
    expect(goesOn.length).toBeGreaterThan(0);
    await view.unmount();
  });
});

/** Stream `text` in small flushes (the last one mid-line when it ends so), then settle it as `final`. */
async function streamedThenSettled(text: string, final = text): Promise<Drawn[]> {
  const view = await render(
    <MarkdownContent content="" streaming mathFormat={formatAssistantMathExpr} />,
  );
  for (let end = 40; end < text.length + 40; end += 40) {
    const content = text.slice(0, Math.min(end, text.length));
    await act(async () => {
      view.rerender(
        <MarkdownContent content={content} streaming mathFormat={formatAssistantMathExpr} />,
      );
    });
  }
  await act(async () => {
    view.rerender(<MarkdownContent content={final} mathFormat={formatAssistantMathExpr} />);
  });
  const blocks = blocksOf(view.toJSON() as Json);
  await view.unmount();
  return blocks;
}

async function drawnSettled(content: string): Promise<Drawn[]> {
  const view = await render(<MarkdownContent content={content} mathFormat={formatAssistantMathExpr} />);
  const blocks = blocksOf(view.toJSON() as Json);
  await view.unmount();
  return blocks;
}

describe("a streamed reply that settles", () => {
  it.each(replies)(
    "%s looks the same as the reply drawn settled",
    async (_name, text) => {
      expect(JSON.stringify(await streamedThenSettled(text))).toBe(
        JSON.stringify(await drawnSettled(text)),
      );
    },
    120_000,
  );

  it("looks the same when the saved reply differs from what streamed", async () => {
    const text = STREAMING_REPLIES.tips;
    const lines = text.split("\n");
    // The server's saved text: a line in the middle reworded, and the long list cut short.
    const middle = Math.floor(lines.length / 3);
    const reworded = [...lines.slice(0, middle), "A reworded line.", ...lines.slice(middle + 1)].join("\n");
    const listCut = text.slice(0, Math.floor(text.length * 0.6)).replace(/\n[^\n]*$/, "\n\nThat is all.");
    for (const final of [reworded, listCut]) {
      expect(JSON.stringify(await streamedThenSettled(text, final))).toBe(
        JSON.stringify(await drawnSettled(final)),
      );
    }
  }, 120_000);

  it("draws a list's end again when the saved reply ends the list where a piece did", async () => {
    const items = Array.from({ length: 14 }, (_, i) => `- Item ${i + 1}: ${"plain words ".repeat(6).trim()}`);
    const text = `Intro.\n\n${items.join("\n")}\n\nDone.\n`;
    const streamed = advanceStreamBlocks(null, text, text.length);
    expect(streamed.continued[0]).toBe(true);
    // The saved reply stops the list where the first piece ended: a line that
    // belongs to the item above, not a list that goes on.
    const final = `${streamed.chunks[0]}That is all.\n`;
    expect(JSON.stringify(await streamedThenSettled(text, final))).toBe(
      JSON.stringify(await drawnSettled(final)),
    );
  }, 120_000);
});
