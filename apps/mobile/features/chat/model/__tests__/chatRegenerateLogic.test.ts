import {
  popLastAssistantMessage,
  restoreAssistantMessage,
} from "@/features/chat/model/regenerateLogic";
import type { Message } from "@/lib/api";

const assistant: Message = {
  id: "a1",
  role: "assistant",
  content: "Hello",
  model: "free-chat",
  created_at: "2026-01-01T00:00:00Z",
};

const user: Message = {
  id: "u1",
  role: "user",
  content: "Hi",
  model: null,
  created_at: "2026-01-01T00:00:01Z",
};

describe("chatRegenerateLogic", () => {
  it("popLastAssistantMessage removes trailing assistant and returns backup", () => {
    const { backup, messages } = popLastAssistantMessage([user, assistant]);
    expect(backup).toEqual(assistant);
    expect(messages).toEqual([user]);
  });

  it("popLastAssistantMessage is no-op when last message is not assistant", () => {
    const { backup, messages } = popLastAssistantMessage([user]);
    expect(backup).toBeNull();
    expect(messages).toEqual([user]);
  });

  it("restoreAssistantMessage appends backup when missing", () => {
    expect(restoreAssistantMessage([user], assistant)).toEqual([user, assistant]);
  });

  it("restoreAssistantMessage avoids duplicate ids", () => {
    expect(restoreAssistantMessage([user, assistant], assistant)).toEqual([
      user,
      assistant,
    ]);
  });

  const streaming: Message = { ...assistant, id: "streaming", content: "" };

  it("restoreAssistantMessage puts the backup where its replacement streamed, above a message sent since", () => {
    const sentSince: Message = { ...user, id: "local-2", content: "next" };
    expect(restoreAssistantMessage([user, streaming, sentSince], assistant)).toEqual([
      user,
      assistant,
      sentSince,
    ]);
  });

  it("restoreAssistantMessage drops the streaming row, with or without a backup to put back", () => {
    expect(restoreAssistantMessage([user, streaming], null)).toEqual([user]);
    expect(restoreAssistantMessage([user, assistant, streaming], assistant)).toEqual([user, assistant]);
  });
});
