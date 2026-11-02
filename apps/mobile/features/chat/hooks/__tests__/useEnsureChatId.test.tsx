import { act, renderHook } from "@testing-library/react-native";

import { useEnsureChatId } from "@/features/chat/hooks/useEnsureChatId";

function draft(created: string | null) {
  const value = {
    creatingRef: { current: false },
    skipLoadForChatIdRef: { current: null as string | null },
    draftChatIdRef: { current: created as string | null },
    setDraftChatId: jest.fn(),
    prepareDraftChat: jest.fn(),
  };
  let creatingDuringPrepare: boolean | null = null;
  value.prepareDraftChat.mockImplementation(async () => {
    creatingDuringPrepare = value.creatingRef.current;
    return created;
  });
  return { value, creatingDuringPrepare: () => creatingDuringPrepare };
}

async function setup(chatId: string | null, chatDraft: ReturnType<typeof draft>["value"]) {
  const options = {
    chatId,
    selectedModel: "free-chat",
    draft: chatDraft,
    setChatId: jest.fn(),
    setChatTitle: jest.fn(),
    router: { setParams: jest.fn() },
  };
  const { result } = await renderHook(() => useEnsureChatId(options));
  return { ensureChatId: result.current, options };
}

it("returns the open chat without making one", async () => {
  const chatDraft = draft("never");
  const { ensureChatId } = await setup("chat-1", chatDraft.value);
  await expect(ensureChatId()).resolves.toBe("chat-1");
  expect(chatDraft.value.prepareDraftChat).not.toHaveBeenCalled();
});

it("makes a new chat the open one when none is open", async () => {
  const chatDraft = draft("new-1");
  const { ensureChatId, options } = await setup(null, chatDraft.value);
  let id: string | null = null;
  await act(async () => { id = await ensureChatId(); });
  expect(id).toBe("new-1");
  expect(chatDraft.value.prepareDraftChat).toHaveBeenCalledWith("free-chat");
  expect(chatDraft.creatingDuringPrepare()).toBe(true);
  expect(chatDraft.value.creatingRef.current).toBe(false);
  expect(chatDraft.value.skipLoadForChatIdRef.current).toBe("new-1");
  expect(chatDraft.value.draftChatIdRef.current).toBeNull();
  expect(options.setChatTitle).toHaveBeenCalledWith(null);
  expect(options.setChatId).toHaveBeenCalledWith("new-1");
  expect(chatDraft.value.setDraftChatId).toHaveBeenCalledWith(null);
  expect(options.router.setParams).toHaveBeenCalledWith({ chatId: "new-1" });
});

it("throws when no chat can be made, and leaves nothing half made", async () => {
  const chatDraft = draft(null);
  const { ensureChatId, options } = await setup(null, chatDraft.value);
  await expect(ensureChatId()).rejects.toThrow("Could not create chat");
  expect(options.setChatId).not.toHaveBeenCalled();
  expect(chatDraft.value.creatingRef.current).toBe(false);
});
