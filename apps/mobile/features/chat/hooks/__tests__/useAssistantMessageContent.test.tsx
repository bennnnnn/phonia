import { renderHook } from "@testing-library/react-native";

import { useAssistantMessageContent } from "@/features/chat/hooks/useAssistantMessageContent";
import type { Message } from "@/lib/api";

const SAVED_ID = "0192f5c4-6f1e-7c3a-9a55-0c2f3e4d5a6b";
const AFTER_CUTOVER = "2026-12-01T10:00:00.000000Z";
const BEFORE_CUTOVER = "2026-10-01T10:00:00.000000Z";

function row(id: string, createdAt: string): Message {
  return {
    id,
    role: "assistant",
    content: "Turn at **40 km/h**.",
    model: "free-chat",
    created_at: createdAt,
  };
}

async function presented(
  message: Message,
  options: { liveContent?: string; isUser?: boolean } = {},
): Promise<boolean> {
  const { result } = await renderHook(() =>
    useAssistantMessageContent({
      message,
      liveContent: options.liveContent,
      layoutFrozen: false,
      isGenerating: options.liveContent !== undefined,
      isUser: options.isUser ?? false,
    }),
  );
  return result.current.markdownPresented;
}

describe("useAssistantMessageContent markdownPresented", () => {
  it("is true for a reply the server presented and saved", async () => {
    expect(await presented(row(SAVED_ID, AFTER_CUTOVER))).toBe(true);
  });

  it("is false for a reply saved before the cut-over, so the phone presents it", async () => {
    expect(await presented(row(SAVED_ID, BEFORE_CUTOVER))).toBe(false);
  });

  it("is false while the draft streams and for a locally kept stopped reply", async () => {
    expect(await presented(row("streaming", AFTER_CUTOVER), { liveContent: "Turn at**40" })).toBe(
      false,
    );
    expect(await presented(row(SAVED_ID, AFTER_CUTOVER), { liveContent: "Turn at**40" })).toBe(
      false,
    );
    expect(await presented(row("streamed-1798761600000", AFTER_CUTOVER))).toBe(false);
  });

  it("is false for the reply that just streamed in, so it stays as it was drawn", async () => {
    const streamedHere = { ...row(SAVED_ID, AFTER_CUTOVER), renderKey: "stream-1798761600000" };
    expect(await presented(streamedHere)).toBe(false);
  });

  it("is false for the user's own message", async () => {
    expect(await presented(row(SAVED_ID, AFTER_CUTOVER), { isUser: true })).toBe(false);
  });
});
