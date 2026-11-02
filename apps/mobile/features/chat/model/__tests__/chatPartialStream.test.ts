import type { Message } from "@/lib/api";
import { replaceStreamingMessageWithPartial } from "@/features/chat/model/partialStream";

const userMessage: Message = {
  id: "user-1",
  role: "user",
  content: "Explain this",
  model: null,
  created_at: "2026-08-21T00:00:00Z",
};

const streamingMessage: Message = {
  id: "streaming",
  role: "assistant",
  content: "",
  model: "smart-chat",
  created_at: "2026-08-21T00:00:01Z",
};

describe("replaceStreamingMessageWithPartial", () => {
  it("keeps partial SSE content instead of dropping the reply", () => {
    const result = replaceStreamingMessageWithPartial(
      [userMessage, streamingMessage],
      "A partial but useful answer",
      {
        content: "A partial but useful answer",
        search_sources: [{ title: "Source", url: "https://example.com" }],
      },
      "streamed-1",
    );

    expect(result).toEqual([
      userMessage,
      expect.objectContaining({
        id: "streamed-1",
        content: "A partial but useful answer",
        search_sources: [{ title: "Source", url: "https://example.com" }],
      }),
    ]);
  });

  it("does not alter completed messages", () => {
    expect(
      replaceStreamingMessageWithPartial(
        [userMessage],
        "partial",
        { content: "partial" },
        "streamed-1",
      ),
    ).toEqual([userMessage]);
  });
});
