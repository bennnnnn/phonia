import { act, render } from "@testing-library/react-native";

import { ChatMessageRow } from "@/features/chat/components/ChatMessageRow";
import type { Message } from "@/lib/api";

let mockBubbleProps: {
  onRegenerate?: () => void;
  onRetryImageGen?: () => void;
  liveContent?: string;
  isGenerating?: boolean;
} = {};
const mockDraftReads: boolean[] = [];

jest.mock("@/features/chat/components/MessageBubble", () => {
  const { Text: MockText } =
    jest.requireActual("react-native") as typeof import("react-native");
  return {
    MessageBubble: (props: { message: Message; liveContent?: string }) => {
      mockBubbleProps = props;
      // Stand-in for any part of a bubble outside the markdown boundary
      // (images, places, proposal cards, sources) meeting data it can't draw.
      if (props.message.content === "bad") throw new Error("cannot draw this block");
      return <MockText>{props.liveContent ?? props.message.content}</MockText>;
    },
  };
});
let mockDraft: { content: string } | null = null;
jest.mock("@/features/chat/context/StreamingDraftContext", () => ({
  useStreamingDraft: (enabled: boolean) => {
    mockDraftReads.push(enabled);
    return enabled ? mockDraft : null;
  },
}));
jest.mock("@/lib/theme", () => ({ useTheme: () => ({ textSecondary: "#666" }) }));

const message = (id: string, content: string): Message =>
  ({
    id,
    role: "assistant",
    content,
    model: "free-chat",
    created_at: "2026-01-01T00:00:00Z",
  }) as Message;

const rowProps = {
  priorUserText: null,
  streamVisualActive: false,
  lastAssistantId: null,
  selectedModel: "free-chat",
  highlightedMessageId: null,
  sendingMessageId: null,
  onRegenerate: jest.fn(),
  onFeedback: jest.fn(),
};

afterEach(() => {
  mockDraft = null;
  mockDraftReads.length = 0;
});

describe("ChatMessageRow", () => {
  it.each([
    ["a failed picture", { image_gen_failure: "failed" }, true],
    ["a stopped picture", { image_gen_failure: "canceled" }, true],
    ["a picture the day's cap refused", { image_gen_failure: "failed", image_gen_refused: true }, false],
  ] as const)("offers Retry under %s only when a retry can go differently", async (_label, failure, retry) => {
    const item = { ...message("image-gen-failed", ""), ...failure };
    await render(<ChatMessageRow {...rowProps} item={item} onRetryImageGen={jest.fn()} />);
    expect(Boolean(mockBubbleProps.onRetryImageGen)).toBe(retry);
  });

  it("keeps the prebound regenerate callback stable across renders", async () => {
    const item = message("assistant-1", "Reply");
    const onRegenerate = jest.fn();
    const props = { ...rowProps, item, priorUserText: "Question", lastAssistantId: item.id, onRegenerate };
    const view = await render(<ChatMessageRow {...props} highlightedMessageId={null} />);
    const first = mockBubbleProps.onRegenerate;

    await view.rerender(<ChatMessageRow {...props} highlightedMessageId="other" />);

    expect(mockBubbleProps.onRegenerate).toBe(first);
    first?.();
    expect(onRegenerate).toHaveBeenCalledWith("free-chat");
  });

  it("reads the live draft only in the row a reply streams into", async () => {
    mockDraft = { content: "Streaming text" };
    const saved = await render(<ChatMessageRow item={message("a", "Saved text")} {...rowProps} />);
    expect(saved.getByText("Saved text")).toBeTruthy();
    expect(mockDraftReads.every((enabled) => !enabled)).toBe(true);
    await saved.unmount();

    const live = await render(
      <ChatMessageRow item={message("streaming", "")} {...rowProps} live streamVisualActive />,
    );
    expect(live.getByText("Streaming text")).toBeTruthy();
    expect(mockBubbleProps.isGenerating).toBe(true);
  });

  it.each([
    ["A few", "some", "hi", "Hey bini"],
    ["Lots", "more", "hi", "Hey bini 👋"],
    ["None, after the user waved", "off", "hi 👋", "Hey bini 👋"],
  ] as const)("streams a greeting as it will be saved at %s", async (_label, emojiUse, said, shown) => {
    // The server drops a sentence's emoji at A few: a draft that kept it lost it on save.
    mockDraft = { content: "Hey bini 👋" };
    await render(
      <ChatMessageRow
        {...rowProps}
        item={message("streaming", "")}
        live
        emojiUse={emojiUse}
        priorUserText={said}
      />,
    );
    expect(mockBubbleProps.liveContent).toBe(shown);
  });

  it("goes on drawing the saved reply when the turn ends, in the same row", async () => {
    mockDraft = { content: "The whole answer" };
    const streaming = { ...message("streaming", ""), renderKey: "stream-1" };
    const view = await render(
      <ChatMessageRow item={streaming} {...rowProps} live streamVisualActive lastAssistantId="streaming" />,
    );
    const before = view.getByText("The whole answer");

    const saved = { ...streaming, id: "m-1", content: "The whole answer" };
    await view.rerender(<ChatMessageRow item={saved} {...rowProps} lastAssistantId="m-1" />);
    // The same host view, updated: not created again.
    expect(view.getByText("The whole answer")).toBe(before);
    expect(mockBubbleProps.liveContent).toBeUndefined();
    expect(mockBubbleProps.isGenerating).toBe(false);
    expect(mockBubbleProps.onRegenerate).toEqual(expect.any(Function));
  });
});

describe("ChatMessageRow stall hint (S7.2)", () => {
  const streamingItem = message("streaming", "");
  const props = {
    ...rowProps,
    item: streamingItem,
    priorUserText: "Question",
    streamVisualActive: true,
    live: true,
  };

  beforeEach(() => {
    jest.useFakeTimers();
  });
  afterEach(() => {
    jest.useRealTimers();
  });

  it("says it is still working, and that Stop ends it, once text stops arriving for 20 s", async () => {
    mockDraft = { content: "The first part of the answer" };
    const view = await render(<ChatMessageRow {...props} />);
    await act(async () => { jest.advanceTimersByTime(19_000); });
    expect(view.queryByTestId("stream-silence-hint")).toBeNull();
    await act(async () => { jest.advanceTimersByTime(1_500); });
    expect(view.getByText("chat.still_working")).toBeTruthy();

    // A new token clears it and restarts the wait.
    mockDraft = { content: "The first part of the answer, then more" };
    await view.rerender(<ChatMessageRow {...props} item={{ ...streamingItem }} />);
    expect(view.queryByTestId("stream-silence-hint")).toBeNull();
  });

  it("says nothing before the first token or once the reply has ended", async () => {
    mockDraft = { content: "" };
    const waiting = await render(<ChatMessageRow {...props} />);
    await act(async () => { jest.advanceTimersByTime(60_000); });
    expect(waiting.queryByTestId("stream-silence-hint")).toBeNull();
    await waiting.unmount();

    mockDraft = { content: "Done." };
    const ended = await render(<ChatMessageRow {...props} streamVisualActive={false} />);
    await act(async () => { jest.advanceTimersByTime(60_000); });
    expect(ended.queryByTestId("stream-silence-hint")).toBeNull();
  });
});

describe("chat rows contain a render error", () => {
  let consoleError: jest.SpyInstance;
  beforeEach(() => {
    // React logs every caught render error; the assertions below are the point.
    consoleError = jest.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    consoleError.mockRestore();
  });

  it("shows one quiet line for a reply that cannot be drawn and keeps the rest", async () => {
    const view = await render(
      <>
        <ChatMessageRow item={message("a", "fine before")} {...rowProps} />
        <ChatMessageRow item={message("b", "bad")} {...rowProps} />
        <ChatMessageRow item={message("c", "fine after")} {...rowProps} />
      </>,
    );
    expect(view.getByText("fine before")).toBeTruthy();
    expect(view.getByText("chat.message_render_failed")).toBeTruthy();
    expect(view.getByText("fine after")).toBeTruthy();
  });

  it("draws the next reply when the list reuses a failed row", async () => {
    const view = await render(<ChatMessageRow item={message("b", "bad")} {...rowProps} />);
    expect(view.getByText("chat.message_render_failed")).toBeTruthy();
    await view.rerender(<ChatMessageRow item={message("c", "recycled")} {...rowProps} />);
    expect(view.getByText("recycled")).toBeTruthy();
    expect(view.queryByText("chat.message_render_failed")).toBeNull();
  });

  it("contains a streaming reply that cannot be drawn", async () => {
    const view = await render(
      <ChatMessageRow item={message("streaming", "bad")} {...rowProps} live streamVisualActive />,
    );
    expect(view.getByText("chat.message_render_failed")).toBeTruthy();
  });
});
