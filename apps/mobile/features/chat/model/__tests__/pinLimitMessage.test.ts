import { setChatPinned, type ChatOperationContext } from "@/features/chat/model/chatOperations";
import { api } from "@/lib/api";
import { ApiRequestError } from "@/lib/api/errorBody";

jest.mock("@/lib/api", () => ({ api: { setPin: jest.fn() } }));
jest.mock("@/features/chat/drawer/drawer", () => ({ abandonActiveChatIfDeleted: jest.fn() }));
jest.mock("@/features/chat/model/chatListCache", () => ({ getCachedChat: jest.fn(), peekCreatedChat: jest.fn() }));
jest.mock("@/features/chat/model/messageCache", () => ({ clearCachedChatMessages: jest.fn() }));
jest.mock("@/features/chat/model/mutationLock", () => ({ beginChatMutation: () => () => {} }));

// The cap is the server's (20 pinned chats): the words carry its number, never one of their own.
it("names the server's pin cap in the refusal", async () => {
  jest.mocked(api.setPin).mockRejectedValueOnce(
    new ApiRequestError(409, JSON.stringify({ detail: { code: "pin_limit", message: "full", limit: 20 } })),
  );
  const failure = jest.fn();
  const t = jest.fn((key: string, options?: Record<string, unknown>) =>
    options ? `${key}:${JSON.stringify(options)}` : key,
  );
  const ctx: ChatOperationContext = {
    token: "token",
    session: 1,
    list: { patch: jest.fn(), insert: jest.fn(), remove: jest.fn() },
    signedIn: () => true,
    shown: () => true,
    banner: jest.fn(),
    failure,
    t,
  };

  await setChatPinned(ctx, { id: "one", title: "A chat", pinned: false, archived: false }, true);

  expect(failure).toHaveBeenCalledWith('chat.pin_limit:{"limit":20}');
});
