import type { Message } from "@/lib/api/types";
import { applyLiveTalkChatEvent } from "@/features/speech/model/liveTalkEvents";

describe("liveTalkEvents", () => {
  it("reconciles an old turn without moving it below the next utterance", () => {
    let rows: Message[] = [];
    for (const id of ["old", "new"]) {
      rows = applyLiveTalkChatEvent(rows, id, { type: "user", text: id });
      rows = applyLiveTalkChatEvent(rows, id, { type: "assistant", text: `${id} reply` });
    }
    const next = applyLiveTalkChatEvent(rows, "old", {
      type: "done", remaining: 0, limit: 0,
      user_message: { ...rows[0], id: "saved-user" },
      assistant_message: { ...rows[1], id: "saved-assistant" },
    });
    expect(next.map((row) => row.id)).toEqual([
      "saved-user", "saved-assistant", "local-live-user-new", "local-live-assistant-new",
    ]);
    expect(applyLiveTalkChatEvent([], "old", { type: "done", remaining: 0, limit: 0,
      user_message: next[0], assistant_message: next[1] })).toEqual([]);
  });
  it("upserts local bubbles then swaps in persisted messages", () => {
    const user: Message = {
      id: "u1",
      role: "user",
      content: "Hi",
      model: null,
      created_at: "2026-01-01T00:00:00Z",
    };
    const assistant: Message = {
      id: "a1",
      role: "assistant",
      content: "Hello",
      model: "live-talk-model",
      created_at: "2026-01-01T00:00:01Z",
    };
    let messages: Message[] = [];
    messages = applyLiveTalkChatEvent(messages, "t1", { type: "user", text: "Hi" });
    messages = applyLiveTalkChatEvent(messages, "t1", { type: "assistant", text: "Hel" });
    messages = applyLiveTalkChatEvent(messages, "t1", { type: "assistant", text: "Hello" });
    expect(messages).toHaveLength(2);
    expect(messages[1]?.content).toBe("Hello");
    messages = applyLiveTalkChatEvent(messages, "t1", {
      type: "done",
      remaining: 29,
      limit: 30,
      user_message: user,
      assistant_message: assistant,
    });
    expect(messages.map((row) => row.id)).toEqual(["u1", "a1"]);
  });
});
