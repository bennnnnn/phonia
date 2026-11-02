import {
  findLastAssistantId,
  isChatStreamActive,
  nextUserTextFor,
  priorUserTextFor,
  streamVisualActiveForRow,
} from "@/features/chat/model/messageLogic";
import type { Message } from "@/lib/api";

describe("chatMessageLogic", () => {
  it("findLastAssistantId returns the latest assistant message", () => {
    const messages = [
      { id: "1", role: "user", content: "hi" },
      { id: "2", role: "assistant", content: "hello" },
      { id: "3", role: "user", content: "again" },
      { id: "4", role: "assistant", content: "sure" },
    ] as Message[];

    expect(findLastAssistantId(messages)).toBe("4");
    expect(findLastAssistantId([])).toBeNull();
    expect(findLastAssistantId([{ id: "1", role: "user", content: "x" } as Message])).toBeNull();
  });

  it("isChatStreamActive stays true during post-stream finalization", () => {
    expect(isChatStreamActive(true, false)).toBe(true);
    expect(isChatStreamActive(false, true)).toBe(true);
    expect(isChatStreamActive(false, false)).toBe(false);
  });

  describe("streamVisualActiveForRow", () => {
    it("returns a stable false for user rows regardless of stream state", () => {
      expect(streamVisualActiveForRow("user", "u1", "a2", true, false)).toBe(false);
      expect(streamVisualActiveForRow("user", "u1", "a2", false, false)).toBe(false);
    });

    it("returns the real value for the row matching lastAssistantId", () => {
      expect(streamVisualActiveForRow("assistant", "a2", "a2", true, false)).toBe(true);
      expect(streamVisualActiveForRow("assistant", "a2", "a2", false, true)).toBe(true);
    });

    it("returns a stable false for other assistant rows regardless of stream state", () => {
      expect(streamVisualActiveForRow("assistant", "a1", "a2", true, false)).toBe(false);
      expect(streamVisualActiveForRow("assistant", "a1", "a2", false, true)).toBe(false);
    });

    it("returns false for a user row when no turn is active", () => {
      expect(streamVisualActiveForRow("user", "u1", null, false, false)).toBe(false);
    });
  });

  describe("nextUserTextFor", () => {
    const messages = [
      { id: "1", role: "user", content: "how can I understand integrals?" },
      { id: "2", role: "assistant", content: "Two quick questions" },
      { id: "3", role: "user", content: "Studied it before: No, never" },
      { id: "4", role: "assistant", content: "Then start with areas." },
    ] as Message[];

    it("returns the user message that answered an assistant reply", () => {
      expect(nextUserTextFor(messages, 1)).toBe("Studied it before: No, never");
    });

    it("returns null for the newest reply, a user message, or an index past the end", () => {
      expect(nextUserTextFor(messages, 3)).toBeNull();
      expect(nextUserTextFor(messages, 0)).toBeNull();
      expect(nextUserTextFor(messages, 99)).toBeNull();
    });
  });

  describe("priorUserTextFor", () => {
    const messages = [
      { id: "1", role: "user", content: "what's the weather" },
      { id: "2", role: "assistant", content: "sunny" },
      { id: "3", role: "assistant", content: "anything else?" },
    ] as Message[];

    it("returns the preceding user message's content for an assistant reply", () => {
      expect(priorUserTextFor(messages, 1)).toBe("what's the weather");
    });

    it("returns null when the preceding item isn't a user message", () => {
      expect(priorUserTextFor(messages, 2)).toBeNull();
    });

    it("returns null for a user message", () => {
      expect(priorUserTextFor(messages, 0)).toBeNull();
    });

    it("returns null at index 0 even if it were an assistant message", () => {
      const leading = [{ id: "1", role: "assistant", content: "hi" }] as Message[];
      expect(priorUserTextFor(leading, 0)).toBeNull();
    });

    it("returns null for an out-of-range index", () => {
      expect(priorUserTextFor(messages, 99)).toBeNull();
    });
  });
});
