import {
  isFreshStreamRenderKey,
  latchStartRenderingFromBottom,
  messageListItemType,
  messageListKey,
  shouldStartRenderingFromBottom,
} from "@/lib/messageListLayout";

describe("messageListLayout", () => {
  it("keeps the first turn under the header", () => {
    expect(
      shouldStartRenderingFromBottom({ messageCount: 0, hasMoreOlder: false }),
    ).toBe(false);
    expect(
      shouldStartRenderingFromBottom({ messageCount: 1, hasMoreOlder: false }),
    ).toBe(false);
    expect(
      shouldStartRenderingFromBottom({ messageCount: 2, hasMoreOlder: false }),
    ).toBe(false);
    expect(
      shouldStartRenderingFromBottom({ messageCount: 4, hasMoreOlder: false }),
    ).toBe(false);
    expect(
      shouldStartRenderingFromBottom({ messageCount: 0, hasMoreOlder: true }),
    ).toBe(false);
    expect(
      shouldStartRenderingFromBottom({ messageCount: 1, hasMoreOlder: true }),
    ).toBe(true);
  });

  it("does not promote a short in-progress thread to bottom pinning", () => {
    const started = latchStartRenderingFromBottom({
      chatKey: "new:live",
      previousChatKey: "new:empty",
      previousValue: false,
      messageCount: 2,
      hasMoreOlder: false,
    });
    expect(started.value).toBe(false);
    const grew = latchStartRenderingFromBottom({
      chatKey: "new:live",
      previousChatKey: started.chatKey,
      previousValue: started.value,
      messageCount: 3,
      hasMoreOlder: false,
    });
    expect(grew.value).toBe(false);
    const named = latchStartRenderingFromBottom({
      chatKey: "chat-1:live",
      previousChatKey: grew.chatKey,
      previousValue: grew.value,
      messageCount: 4,
      hasMoreOlder: false,
    });
    expect(named.value).toBe(false);
    const openedLong = latchStartRenderingFromBottom({
      chatKey: "chat-2:live",
      previousChatKey: "",
      previousValue: false,
      messageCount: 8,
      hasMoreOlder: false,
    });
    expect(openedLong.value).toBe(false);
    const withHistory = latchStartRenderingFromBottom({
      chatKey: "chat-2:live",
      previousChatKey: openedLong.chatKey,
      previousValue: openedLong.value,
      messageCount: 8,
      hasMoreOlder: true,
    });
    expect(withHistory.value).toBe(true);
  });

  it("uses role for user rows", () => {
    expect(messageListItemType({ id: "msg-2", role: "user" })).toBe("user");
  });

  it("distinguishes assistant row layouts by fenced content", () => {
    expect(messageListItemType({ id: "streaming", role: "assistant" })).toBe("assistant");
    expect(
      messageListItemType({
        id: "msg-quiz",
        role: "assistant",
        content: "```vocab_quiz\n{\"word\":\"hola\"}\n```",
      }),
    ).toBe("assistant");
    expect(
      messageListItemType({
        id: "msg-vocab",
        role: "assistant",
        content: "```vocab_card\n{\"word\":\"hola\",\"definition\":\"hello\"}\n```",
      }),
    ).toBe("assistant");
    // Retired calendar event proposals are stripped for display: a plain row.
    expect(
      messageListItemType({
        id: "msg-cal",
        role: "assistant",
        content: '```calendar_proposal\n{"title":"Standup"}\n```',
      }),
    ).toBe("assistant");
  });

  it("prefers renderKey for FlashList identity", () => {
    expect(messageListKey({ id: "streaming", renderKey: "stream-1" })).toBe("stream-1");
    expect(messageListKey({ id: "msg-1" })).toBe("msg-1");
  });

  it("detects fresh stream render keys", () => {
    expect(isFreshStreamRenderKey("stream-171")).toBe(true);
    expect(isFreshStreamRenderKey("msg-1")).toBe(false);
    expect(isFreshStreamRenderKey(undefined)).toBe(false);
  });
});
