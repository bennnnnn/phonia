import React, { memo, useLayoutEffect, useState } from "react";
import { AppState, Text } from "react-native";
import { act, render, waitFor } from "@testing-library/react-native";

import { useChatRouteLoader } from "@/features/chat/hooks/useChatRouteLoader";
import { api, type Message } from "@/lib/api";
import { getCachedChat } from "@/features/chat/model/chatListCache";
import {
  clearAllCachedChatMessages,
  clearCachedChatMessages,
  isCachedChatPageFresh,
  keepCachedChatPage,
  peekCachedChatPage,
  readCachedChatMessages,
} from "@/features/chat/model/messageCache";
import { OPENED_PAGE_WAIT_MS, whenOpenedPageSettled, withdrawFromOpenedPage } from "@/features/chat/model/openedPage";
import {
  resetComposerAttachmentQueue,
  takeQueuedComposerAttachment,
} from "@/features/attachments/model/pendingComposerAttachment";
import type { PendingAttachment } from "@/features/attachments/model/attachments";
import type { PendingSend } from "@/features/chat/model/sendLogic";


let mockSession = 0;
let mockRevision = 0;
let mockChatChange: ((id: string, patch: Record<string, unknown> | null) => void) | undefined;
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
jest.mock("@/features/chat/drawer/drawer", () => ({
  getChatMutationRevision: () => mockRevision,
  subscribeChatChanges: (fn: typeof mockChatChange) => { mockChatChange = fn; return () => { mockChatChange = undefined; }; },
  removeChatGlobal: jest.fn(),
}));
jest.mock("@/lib/api/client", () => ({
  ApiRequestError: class extends Error { status: number; constructor(status: number) { super("Request failed"); this.status = status; } },
}));
import { ApiRequestError } from "@/lib/api/client";

jest.mock("expo-router", () => ({
  useFocusEffect: () => undefined,
  useRouter: () => ({}),
}));
jest.mock("@/lib/api", () => ({
  api: {
    getChat: jest.fn(),
    listMessages: jest.fn(),
  },
}));
jest.mock("@/features/chat/model/chatListCache", () => {
  const getCachedChat = jest.fn((_id: string): unknown => undefined);
  return { getCachedChat, getFetchedChat: (id: string) => getCachedChat(id) };
});
// The kept pages are real; the file behind them is not.
jest.mock("expo-file-system/legacy", () => ({ cacheDirectory: null }));
jest.mock("@/features/chat/model/messageCache", () => {
  const actual = jest.requireActual("@/features/chat/model/messageCache");
  return {
    ...actual,
    clearCachedChatMessages: jest.fn(actual.clearCachedChatMessages),
    keepCachedChatPage: jest.fn(actual.keepCachedChatPage),
    readCachedChatMessages: jest.fn(async () => null),
  };
});

jest.mock("@/features/chat/hooks/useChatTitlePolling", () => ({
  useChatTitlePolling: () => ({
    titleGenerating: false,
    pollForTitle: jest.fn(),
    handleFirstReply: mockHandleFirstReply,
  }),
}));
jest.mock("@/features/chat/hooks/useChatHighlightScroll", () => ({
  useChatHighlightScroll: () => ({ highlightedMessageId: null }),
}));
const mockComposer = { stashFailedDraftForThread: jest.fn() };
jest.mock("@/features/chat/context/ComposerDraftContext", () => ({ useComposerDraftApiOptional: () => mockComposer }));


const mockHandleFirstReply = jest.fn();
const setChatId = jest.fn();
const setMessages = jest.fn();

function Probe() {
  const result = useChatRouteLoader({
    token: "token",
    routeChatId: "chat-1",
    routeHighlightMessage: undefined,
    router: { setParams: jest.fn() } as never,
    draft: {
      draftChatIdRef: { current: null },
      draftProjectIdRef: { current: null },
      draftQuizModeRef: { current: null },
      skipLoadForChatIdRef: { current: null },
      creatingRef: { current: false },
      discardEmptyChat: jest.fn(),
      clearDraftChat: jest.fn(),
      prepareDraftChat: jest.fn(),
    } as never,
    chatId: null,
    setChatId,
    editThread: setMessages,
    messages: [],
    streaming: false,
    stopGeneration: jest.fn(),
    listRef: { current: null },
    showActionBanner: jest.fn(),
    t: (key) => key,
  });
  return <Text>{result.chatLoading ? "loading" : "ready"}</Text>;
}

describe("useChatRouteLoader", () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    await clearAllCachedChatMessages();
    mockSession = 0;
    mockRevision = 0;
    (getCachedChat as jest.Mock).mockReturnValue(undefined);
    (readCachedChatMessages as jest.Mock).mockResolvedValue(null);
    (api.getChat as jest.Mock).mockResolvedValue({
      id: "chat-1",
      title: "Loaded",
      pinned: true,
      archived: false,
      project_id: "project-1",
    });
    (api.listMessages as jest.Mock).mockResolvedValue({
      messages: [{ id: "m1", role: "assistant", content: "Hello" }],
      has_more: false,
    });
  });

  it("skips GET /chats/{id} when the drawer list already has the row", async () => {
    (getCachedChat as jest.Mock).mockReturnValue({
      id: "chat-1",
      title: "From drawer",
      pinned: false,
      archived: false,
      project_id: null,
    });
    await act(async () => {
      render(<Probe />);
    });
    await waitFor(() => {
      expect(api.listMessages).toHaveBeenCalledWith("token", "chat-1", { limit: 40 });
    });
    expect(api.getChat).not.toHaveBeenCalled();
  });

  it("revalidates a cached transcript when reopening a chat", async () => {
    (getCachedChat as jest.Mock).mockReturnValue({
      id: "chat-1",
      title: "From drawer",
      pinned: false,
      archived: false,
      project_id: null,
    });
    (readCachedChatMessages as jest.Mock).mockResolvedValue({
      messages: [{ id: "m1", role: "assistant", content: "Hello" }],
      has_more: false,
      cached_at: new Date(Date.now() - 60_000).toISOString(),
    });
    await act(async () => {
      render(<Probe />);
    });
    await waitFor(() => {
      expect(setChatId).toHaveBeenCalledWith("chat-1");
    });
    expect(api.getChat).not.toHaveBeenCalled();
    expect(api.listMessages).toHaveBeenCalledWith("token", "chat-1", { limit: 40 });
  });

  it("loads chat metadata and messages together for the route", async () => {
    await act(async () => {
      render(<Probe />);
    });

    await waitFor(() => {
      expect(api.getChat).toHaveBeenCalledWith("token", "chat-1");
      expect(api.listMessages).toHaveBeenCalledWith("token", "chat-1", { limit: 40 });
      expect(setChatId).toHaveBeenCalledWith("chat-1");
    });
  });

  it("leaves an in-flight turn running when New chat is tapped", async () => {
    const stopGeneration = jest.fn();
    const setParams = jest.fn();
    let startNewChat: ((opts?: { force?: boolean }) => void) | undefined;
    function StreamingProbe() {
      const result = useChatRouteLoader({
        token: "token",
        routeChatId: "open-1",
        routeHighlightMessage: undefined,
        router: { setParams } as never,
        draft: {
          draftChatIdRef: { current: null },
          draftProjectIdRef: { current: null },
          draftQuizModeRef: { current: null },
          skipLoadForChatIdRef: { current: "open-1" },
          creatingRef: { current: false },
          discardEmptyChat: jest.fn(),
          clearDraftChat: jest.fn(),
          prepareDraftChat: jest.fn(),
        } as never,
        chatId: "open-1",
        setChatId,
        editThread: setMessages,
        messages: [
          {
            id: "u1",
            role: "user",
            content: "Tell me a long story",
            model: null,
            created_at: "t",
          },
          {
            id: "streaming",
            role: "assistant",
            content: "Once upon",
            model: null,
            created_at: "t",
          },
        ],
        streaming: true,
        stopGeneration,
        listRef: { current: null },
        showActionBanner: jest.fn(),
        t: (key) => key,
      });
      useLayoutEffect(() => { startNewChat = result.startNewChat; });
      return <Text>ready</Text>;
    }
    await act(async () => {
      render(<StreamingProbe />);
    });
    await act(async () => {
      startNewChat?.();
    });
    expect(stopGeneration).not.toHaveBeenCalled();
    expect(mockHandleFirstReply).toHaveBeenCalled();
    expect(setChatId).toHaveBeenCalledWith(null);
    expect(setMessages).toHaveBeenCalledWith([], "view_cleared");
    expect(setParams).toHaveBeenCalledWith({ chatId: undefined });
  });

  it("stops an in-flight turn when New chat is forced (deleted chat)", async () => {
    const stopGeneration = jest.fn();
    let startNewChat: ((opts?: { force?: boolean }) => void) | undefined;
    function DeletedProbe() {
      const result = useChatRouteLoader({
        token: "token",
        routeChatId: "open-1",
        routeHighlightMessage: undefined,
        router: { setParams: jest.fn() } as never,
        draft: {
          draftChatIdRef: { current: null },
          draftProjectIdRef: { current: null },
          draftQuizModeRef: { current: null },
          skipLoadForChatIdRef: { current: "open-1" },
          creatingRef: { current: false },
          discardEmptyChat: jest.fn(),
          clearDraftChat: jest.fn(),
          prepareDraftChat: jest.fn(),
        } as never,
        chatId: "open-1",
        setChatId,
        editThread: setMessages,
        messages: [
          {
            id: "u1",
            role: "user",
            content: "hi",
            model: null,
            created_at: "t",
          },
        ],
        streaming: true,
        stopGeneration,
        listRef: { current: null },
        showActionBanner: jest.fn(),
        t: (key) => key,
      });
      useLayoutEffect(() => { startNewChat = result.startNewChat; });
      return <Text>ready</Text>;
    }
    await act(async () => {
      render(<DeletedProbe />);
    });
    await act(async () => {
      startNewChat?.({ force: true });
    });
    expect(stopGeneration).toHaveBeenCalled();
    expect(mockHandleFirstReply).not.toHaveBeenCalled();
  });
});


function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

const message = (id: string, content: string): Message => ({
  id, content, role: "assistant", model: null, created_at: "2026-01-01T00:00:00Z",
});
let routeState: ReturnType<typeof useChatRouteLoader>;
let visibleMessages: Message[];
const routeDraft = {
  draftChatIdRef: { current: null },
  draftProjectIdRef: { current: null },
  skipLoadForChatIdRef: { current: null },
  creatingRef: { current: false },
  discardEmptyChat: jest.fn(),
  clearDraftChat: jest.fn(),
};
const banner = jest.fn();
const translate = (key: string) => key;
let setThread: React.Dispatch<React.SetStateAction<Message[]>>;
function useRouteProbe(routeId: string, token: string, streaming: boolean) {
  const [chatId, updateChatId] = useState<string | null>(null);
  const [messages, updateMessages] = useState<Message[]>([]);
  const result = useChatRouteLoader({
    token, routeChatId: routeId, routeHighlightMessage: undefined,
    router: { setParams: jest.fn() } as never,
    draft: routeDraft as never,
    chatId, setChatId: updateChatId, messages, editThread: updateMessages,
    streaming, stopGeneration: jest.fn(), listRef: { current: null },
    showActionBanner: banner, t: translate,
  });
  useLayoutEffect(() => { routeState = result; visibleMessages = messages; });
  useLayoutEffect(() => { setThread = updateMessages; }, [updateMessages]);
  return { result, messages };
}
function RouteProbe({ routeId, token = "token", streaming = false }: {
  routeId: string;
  token?: string;
  streaming?: boolean;
}) {
  const { result } = useRouteProbe(routeId, token, streaming);
  return <Text>{result.chatLoading ? "loading" : "ready"}</Text>;
}

describe("chat history navigation races", () => {
  const current = message("11111111-1111-1111-1111-111111111111", "A current");
  beforeEach(async () => {
    jest.clearAllMocks();
    await clearAllCachedChatMessages();
    mockSession = 0;
    mockRevision = 0;
    (getCachedChat as jest.Mock).mockReturnValue(undefined);
    (readCachedChatMessages as jest.Mock).mockResolvedValue(null);
    (api.getChat as jest.Mock).mockImplementation(async (_token, id) => ({
      id, title: id, pinned: false, archived: false, project_id: null,
    }));
    (api.listMessages as jest.Mock).mockResolvedValue({ messages: [current], has_more: true });
  });

  it.each([false, true])("ignores older pages after navigation (return to A: %s)", async (returnToA) => {
    const page = deferred<{ messages: Message[]; has_more: boolean }>();
    const view = await render(<RouteProbe routeId="chat-a" />);
    await waitFor(() => expect(routeState.chatLoading).toBe(false));
    (api.listMessages as jest.Mock).mockReturnValueOnce(page.promise);
    let loading!: Promise<void>;
    await act(async () => { loading = routeState.loadOlderMessages(); });
    const other = message("22222222-2222-2222-2222-222222222222", "Current route only");
    (api.listMessages as jest.Mock).mockResolvedValue({ messages: [other], has_more: false });
    await view.rerender(<RouteProbe routeId="chat-b" />);
    await waitFor(() => expect(visibleMessages).toEqual([other]));
    if (returnToA) {
      await view.rerender(<RouteProbe routeId="chat-a" />);
      await waitFor(() => expect(routeState.chatLoading).toBe(false));
    }
    await act(async () => {
      page.resolve({ messages: [message("old-a", "A older")], has_more: true });
      await loading;
    });
    expect(visibleMessages).toEqual([other]);
    expect(routeState.hasMoreOlder).toBe(false);
  });

  it("rejects a retained pagination callback from a previous route", async () => {
    const view = await render(<RouteProbe routeId="chat-a" />);
    await waitFor(() => expect(routeState.chatLoading).toBe(false));
    const loadA = routeState.loadOlderMessages;
    await view.rerender(<RouteProbe routeId="chat-b" />);
    await waitFor(() => expect(routeState.chatLoading).toBe(false));
    (api.listMessages as jest.Mock).mockClear();
    await act(async () => { await loadA(); });
    expect(api.listMessages).not.toHaveBeenCalled();
  });

  it("requests a history page only once for rapid repeated scroll events", async () => {
    const page = deferred<{ messages: Message[]; has_more: boolean }>();
    await render(<RouteProbe routeId="chat-a" />);
    await waitFor(() => expect(routeState.chatLoading).toBe(false));
    (api.listMessages as jest.Mock).mockClear().mockReturnValue(page.promise);
    let first!: Promise<void>;
    let second!: Promise<void>;
    await act(async () => {
      first = routeState.loadOlderMessages();
      second = routeState.loadOlderMessages();
    });
    expect(api.listMessages).toHaveBeenCalledTimes(1);
    await act(async () => {
      page.resolve({ messages: [message("old-a", "A older")], has_more: false });
      await Promise.all([first, second]);
    });
    expect(visibleMessages.map((m) => m.content)).toEqual(["A older", "A current"]);
  });

  it("shows cached history immediately and replaces it with the saved latest turn", async () => {
    const page = deferred<{ messages: Message[]; has_more: boolean }>();
    (readCachedChatMessages as jest.Mock).mockResolvedValue({
      messages: [current], has_more: false, cached_at: new Date().toISOString(),
    });
    (api.listMessages as jest.Mock).mockReturnValue(page.promise);
    await render(<RouteProbe routeId="chat-a" />);
    expect(visibleMessages).toEqual([current]);
    const reply = message("new-reply", "Latest saved answer");
    await act(async () => {
      page.resolve({ messages: [current, reply], has_more: false });
    });
    expect(visibleMessages).toEqual([current, reply]);
    expect(routeState.chatLoading).toBe(false);
  });

  it("preserves the loaded conversation across an access-token refresh", async () => {
    const view = await render(<RouteProbe routeId="chat-a" />);
    await waitFor(() => expect(routeState.chatLoading).toBe(false));
    (api.listMessages as jest.Mock).mockClear();
    (readCachedChatMessages as jest.Mock).mockClear();
    await view.rerender(<RouteProbe routeId="chat-a" token="refreshed" />);
    expect(visibleMessages).toEqual([current]);
    expect(api.listMessages).not.toHaveBeenCalled();
    expect(readCachedChatMessages).not.toHaveBeenCalled();
  });

  it("ignores a history response immediately after logout, before React rerenders", async () => {
    const page = deferred<{ messages: Message[]; has_more: boolean }>();
    (api.listMessages as jest.Mock).mockReturnValue(page.promise);
    await render(<RouteProbe routeId="chat-a" />);
    mockSession++;
    await act(async () => { page.resolve({ messages: [current], has_more: false }); });
    expect(visibleMessages).toEqual([]);
    expect(keepCachedChatPage).not.toHaveBeenCalled();
  });

  it("applies drawer metadata immediately and keeps it when an older load completes", async () => {
    const page = deferred<{ messages: Message[]; has_more: boolean }>();
    (api.listMessages as jest.Mock).mockReturnValue(page.promise);
    await render(<RouteProbe routeId="chat-a" />);
    const updated = { id: "chat-a", title: "Manual title", pinned: true, archived: false, project_id: null };
    await act(async () => {
      mockRevision++;
      (getCachedChat as jest.Mock).mockReturnValue(updated);
      mockChatChange?.("chat-a", updated);
    });
    expect(routeState.chatTitle).toBe("Manual title");
    expect(routeState.pinned).toBe(true);
    await act(async () => { page.resolve({ messages: [current], has_more: false }); });
    expect(routeState.chatTitle).toBe("Manual title");
    expect(routeState.pinned).toBe(true);
    expect(visibleMessages).toEqual([current]);
  });

  it("cannot restore a deleted conversation before route params rerender", async () => {
    const page = deferred<{ messages: Message[]; has_more: boolean }>();
    (api.listMessages as jest.Mock).mockReturnValue(page.promise);
    await render(<RouteProbe routeId="chat-a" />);
    await act(async () => { routeState.startNewChat({ force: true }); });
    await act(async () => { page.resolve({ messages: [current], has_more: false }); });
    expect(visibleMessages).toEqual([]);
    expect(routeState.chatTitle).toBeNull();
    expect(keepCachedChatPage).not.toHaveBeenCalled();
  });

  it("clears cached history when the server confirms the chat is gone", async () => {
    (readCachedChatMessages as jest.Mock).mockResolvedValue({ messages: [current], has_more: true });
    (api.listMessages as jest.Mock).mockRejectedValue(new ApiRequestError(404, "Gone"));
    await render(<RouteProbe routeId="chat-a" />);
    await waitFor(() => expect(routeState.chatLoading).toBe(false));
    expect(visibleMessages).toEqual([]);
    expect(clearCachedChatMessages).toHaveBeenCalledWith("chat-a");
  });

  it("keeps cached history during a temporary service failure", async () => {
    (readCachedChatMessages as jest.Mock).mockResolvedValue({ messages: [current], has_more: true });
    (api.listMessages as jest.Mock).mockRejectedValue(new ApiRequestError(503, "Unavailable"));
    await render(<RouteProbe routeId="chat-a" />);
    await waitFor(() => expect(routeState.chatLoading).toBe(false));
    expect(visibleMessages).toEqual([current]);
    expect(clearCachedChatMessages).not.toHaveBeenCalled();
  });

});

const uuid = (n: number) => `0190a000-0000-7000-8000-${String(n).padStart(12, "0")}`;
const userRow = (id: string, content: string): Message => ({ ...message(id, content), role: "user" });
const listedChat = (id: string, updatedAt = "2026-01-01T00:00:00Z") => ({
  id, title: id, model: "auto", pinned: false, archived: false, created_at: updatedAt, updated_at: updatedAt,
});
type Page = { messages: Message[]; has_more: boolean };

const renders = new Map<string, number>();
const CountedRow = memo(function CountedRow({ item }: { item: Message }) {
  renders.set(item.id, (renders.get(item.id) ?? 0) + 1);
  return <Text>{item.content}</Text>;
});
function ListProbe({ routeId }: { routeId: string }) {
  const { messages } = useRouteProbe(routeId, "token", false);
  return <>{messages.map((item) => <CountedRow key={item.id} item={item} />)}</>;
}

describe("opening a chat", () => {
  const hello = userRow(uuid(1), "Hello");
  const answer = message(uuid(2), "Hi there");
  const sent = userRow("local-9", "Next question");
  const streamingRow = message("streaming", "");
  const picked: PendingAttachment = {
    localUri: "file:///cache/picked.jpg", contentType: "image/jpeg", fileName: "picked.jpg", kind: "image",
  };
  /** A send waiting for the page; a fresh one each time, since the page read marks the turns it hands back. */
  const heldTurn = (): PendingSend => ({
    content: "Next question",
    options: { composerDraft: { text: "Next question", attachment: picked } },
    messageId: "local-9",
    retryingRejected: false,
    dispatched: false,
  });
  const addListener = AppState.addEventListener as unknown as jest.Mock;
  const defaultAddListener = addListener.getMockImplementation();
  const appStateHandlers = new Set<(state: string) => void>();

  beforeEach(async () => {
    jest.clearAllMocks();
    await clearAllCachedChatMessages();
    resetComposerAttachmentQueue();
    mockSession = 0;
    mockRevision = 0;
    appStateHandlers.clear();
    addListener.mockImplementation((_type: string, handler: (state: string) => void) => {
      appStateHandlers.add(handler);
      return { remove: () => appStateHandlers.delete(handler) };
    });
    (getCachedChat as jest.Mock).mockImplementation((id: string) => listedChat(id));
    (readCachedChatMessages as jest.Mock).mockResolvedValue({
      messages: [hello, answer], has_more: false, cached_at: "2026-01-01T00:00:00Z",
    });
    (api.getChat as jest.Mock).mockImplementation(async (_token, id) => listedChat(id));
    // Reset, not just cleared: a read a test queued but never made must not answer the next test.
    (api.listMessages as jest.Mock).mockReset();
    (api.listMessages as jest.Mock).mockResolvedValue({ messages: [hello, answer], has_more: false });
  });
  afterAll(() => addListener.mockImplementation(defaultAddListener));

  /** Open chat-a, then chat-b, both read from the server. */
  async function openAThenB() {
    const view = await render(<RouteProbe routeId="chat-a" />);
    await waitFor(() => expect(routeState.chatLoading).toBe(false));
    const other = [userRow(uuid(5), "Other chat"), message(uuid(6), "Other answer")];
    (api.listMessages as jest.Mock).mockImplementation(async (_token, id) => ({
      messages: id === "chat-a" ? [hello, answer] : other, has_more: false,
    }));
    await view.rerender(<RouteProbe routeId="chat-b" />);
    await waitFor(() => expect(visibleMessages).toEqual(other));
    (api.listMessages as jest.Mock).mockClear();
    (readCachedChatMessages as jest.Mock).mockClear();
    return view;
  }

  it("lets Send work on the painted cached page while the chat loads", async () => {
    (api.listMessages as jest.Mock).mockReturnValue(deferred<Page>().promise);
    await render(<RouteProbe routeId="chat-a" />);
    expect(visibleMessages).toEqual([hello, answer]);
    expect(routeState.chatLoading).toBe(true);
    expect(routeState.historyPending).toBe(false);
    // A page the server has not confirmed is never kept as fresh.
    expect(peekCachedChatPage("chat-a")).toBeNull();
  });

  it("holds Send while nothing of the chat is on screen", async () => {
    (readCachedChatMessages as jest.Mock).mockResolvedValue(null);
    (api.listMessages as jest.Mock).mockReturnValue(deferred<Page>().promise);
    await render(<RouteProbe routeId="chat-a" />);
    expect(routeState.historyPending).toBe(true);
  });

  it("holds a turn sent on the painted page until the page is merged, then lets it go", async () => {
    const page = deferred<Page>();
    (api.listMessages as jest.Mock).mockReturnValue(page.promise);
    const view = await render(<RouteProbe routeId="chat-a" />);
    let verdict: boolean | undefined;
    await act(async () => {
      setThread((prev) => [...prev, sent, streamingRow]);
      view.rerender(<RouteProbe routeId="chat-a" streaming />);
      void whenOpenedPageSettled("chat-a", heldTurn()).then((go) => { verdict = go; });
    });
    expect(verdict).toBeUndefined();
    const elsewhere = [userRow(uuid(3), "From the laptop"), message(uuid(4), "Laptop answer")];
    await act(async () => { page.resolve({ messages: [hello, answer, ...elsewhere], has_more: false }); });
    expect(verdict).toBe(true);
    expect(visibleMessages.map((m) => m.id)).toEqual([uuid(1), uuid(2), uuid(3), uuid(4), "local-9", "streaming"]);
    expect(mockComposer.stashFailedDraftForThread).not.toHaveBeenCalled();
  });

  it("shows the turn once when it settles, and reads the chat only once", async () => {
    const page = deferred<Page>();
    (api.listMessages as jest.Mock).mockReturnValue(page.promise);
    const view = await render(<RouteProbe routeId="chat-a" />);
    await act(async () => {
      setThread((prev) => [...prev, sent, streamingRow]);
      view.rerender(<RouteProbe routeId="chat-a" streaming />);
    });
    await act(async () => { page.resolve({ messages: [hello, answer], has_more: false }); });
    const reply = message(uuid(4), "Reply");
    await act(async () => {
      setThread((prev) => [...prev.filter((m) => m.id !== "streaming"), reply]);
      view.rerender(<RouteProbe routeId="chat-a" />);
    });
    // Follow-up questions land after the reply: nothing reads the chat again.
    await act(async () => {
      setThread((prev) => prev.map((m) => (m.id === reply.id ? { ...m, related_prompts: ["More?"] } : m)));
    });
    expect(visibleMessages.map((m) => m.id)).toEqual([uuid(1), uuid(2), "local-9", uuid(4)]);
    expect(api.listMessages).toHaveBeenCalledTimes(1);
    expect(peekCachedChatPage("chat-a")?.messages.map((m) => m.id)).toEqual([uuid(1), uuid(2), "local-9", uuid(4)]);
    expect(isCachedChatPageFresh("chat-a", undefined)).toBe(true);
  });

  it("needs no hold when a fresh kept page opens the chat without a read", async () => {
    const view = await openAThenB();
    await view.rerender(<RouteProbe routeId="chat-a" />);
    await expect(whenOpenedPageSettled("chat-a", heldTurn())).resolves.toBe(true);
  });

  it("hands a held turn back to New Chat's composer when the chat was deleted elsewhere", async () => {
    const page = deferred<Page>();
    (api.listMessages as jest.Mock).mockReturnValue(page.promise);
    await render(<RouteProbe routeId="chat-a" />);
    let verdict: boolean | undefined;
    void whenOpenedPageSettled("chat-a", heldTurn()).then((go) => { verdict = go; });
    (api.listMessages as jest.Mock).mockRejectedValue(new ApiRequestError(404, "Gone"));
    await act(async () => { page.reject(new ApiRequestError(404, "Gone")); });
    expect(verdict).toBe(false);
    expect(visibleMessages).toEqual([]);
    expect(mockComposer.stashFailedDraftForThread).toHaveBeenCalledWith("new", "Next question");
    expect(takeQueuedComposerAttachment("new")).toBe(picked);
  });

  it("lets a held turn go when the read fails for another reason", async () => {
    const page = deferred<Page>();
    (api.listMessages as jest.Mock).mockReturnValue(page.promise);
    await render(<RouteProbe routeId="chat-a" />);
    const held = whenOpenedPageSettled("chat-a", heldTurn());
    await act(async () => { page.reject(new ApiRequestError(503, "Unavailable")); });
    await expect(held).resolves.toBe(true);
    expect(visibleMessages).toEqual([hello, answer]);
  });

  it("hands a held turn back to its chat's composer when the user leaves the chat first", async () => {
    (api.listMessages as jest.Mock).mockReturnValue(deferred<Page>().promise);
    const view = await render(<RouteProbe routeId="chat-a" />);
    const held = whenOpenedPageSettled("chat-a", heldTurn());
    await view.rerender(<RouteProbe routeId="chat-b" />);
    await expect(held).resolves.toBe(false);
    expect(mockComposer.stashFailedDraftForThread).toHaveBeenCalledWith("chat-a", "Next question");
    expect(takeQueuedComposerAttachment("chat-a")).toBe(picked);
  });

  it("gives nothing of a held turn to the next account", async () => {
    (api.listMessages as jest.Mock).mockReturnValue(deferred<Page>().promise);
    const view = await render(<RouteProbe routeId="chat-a" />);
    const held = whenOpenedPageSettled("chat-a", heldTurn());
    mockSession += 1;
    await view.rerender(<RouteProbe routeId="chat-a" token="next-token" />);
    await expect(held).resolves.toBe(false);
    expect(mockComposer.stashFailedDraftForThread).not.toHaveBeenCalled();
    expect(takeQueuedComposerAttachment("chat-a")).toBeNull();
  });

  /** Paints chat-a from cache, sends a turn and lets the cap send it before `page` lands (fake timers). */
  async function sendPastTheCap(page: Promise<Page>) {
    (api.listMessages as jest.Mock).mockReturnValueOnce(page);
    const view = await render(<RouteProbe routeId="chat-a" />);
    let verdict: boolean | undefined;
    await act(async () => {
      setThread((prev) => [...prev, sent, streamingRow]);
      view.rerender(<RouteProbe routeId="chat-a" streaming />);
      void whenOpenedPageSettled("chat-a", heldTurn()).then((go) => { verdict = go; });
    });
    await act(async () => { await jest.advanceTimersByTimeAsync(OPENED_PAGE_WAIT_MS); });
    expect(verdict).toBe(true);
    return view;
  }
  const settle = () => act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); });

  it("leaves a page that lands while a turn that went first is out unmerged, and reads the chat once it is over", async () => {
    jest.useFakeTimers();
    try {
      const page = deferred<Page>();
      const view = await sendPastTheCap(page.promise);
      // The page may already hold the turn that went out: it stays unmerged while that turn is out.
      const saved = userRow(uuid(3), "Next question");
      await act(async () => { page.resolve({ messages: [hello, answer, saved], has_more: false }); });
      expect(visibleMessages.map((m) => m.id)).toEqual([uuid(1), uuid(2), "local-9", "streaming"]);
      expect(routeState.chatLoading).toBe(false);
      expect(peekCachedChatPage("chat-a")).toBeNull();
      // Its reply is done: the chat is read again, and the turn shows once, as saved.
      const reply = message(uuid(4), "Reply");
      (api.listMessages as jest.Mock).mockResolvedValueOnce({ messages: [hello, answer, saved, reply], has_more: false });
      await act(async () => {
        setThread((prev) => [...prev.filter((m) => m.id !== "streaming"), reply]);
        view.rerender(<RouteProbe routeId="chat-a" />);
      });
      await settle();
      expect(api.listMessages).toHaveBeenCalledTimes(2);
      expect(visibleMessages.map((m) => m.id)).toEqual([uuid(1), uuid(2), uuid(3), uuid(4)]);
      expect(peekCachedChatPage("chat-a")?.messages.map((m) => m.id)).toEqual([uuid(1), uuid(2), uuid(3), uuid(4)]);
    } finally {
      jest.useRealTimers();
    }
  });

  it("merges the late page once the turn that went first was refused (busy) before it landed", async () => {
    jest.useFakeTimers();
    try {
      const page = deferred<Page>();
      const view = await sendPastTheCap(page.promise);
      // The reply the chat was left on still streams: the turn is refused, its bubble and dots go, Retry shows.
      await act(async () => {
        setThread((prev) => prev.filter((m) => m.id !== "local-9" && m.id !== "streaming"));
        view.rerender(<RouteProbe routeId="chat-a" />);
      });
      // The page that lands next holds the user's own last exchange, which the cache lacked.
      const lastExchange = [userRow(uuid(3), "Asked before leaving"), message(uuid(4), "The long reply")];
      await act(async () => { page.resolve({ messages: [hello, answer, ...lastExchange], has_more: false }); });
      expect(visibleMessages.map((m) => m.id)).toEqual([uuid(1), uuid(2), uuid(3), uuid(4)]);
      await settle();
      expect(api.listMessages).toHaveBeenCalledTimes(1);
      expect(isCachedChatPageFresh("chat-a", undefined)).toBe(true);
    } finally {
      jest.useRealTimers();
    }
  });

  it("reads the chat again when follow-up questions change the thread while that read is out", async () => {
    jest.useFakeTimers();
    try {
      const page = deferred<Page>();
      const view = await sendPastTheCap(page.promise);
      const saved = userRow(uuid(3), "Next question");
      await act(async () => { page.resolve({ messages: [hello, answer, saved], has_more: false }); });
      const reply = message(uuid(4), "Reply");
      const firstRead = deferred<Page>();
      (api.listMessages as jest.Mock).mockReturnValueOnce(firstRead.promise);
      await act(async () => {
        setThread((prev) => [...prev.filter((m) => m.id !== "streaming"), reply]);
        view.rerender(<RouteProbe routeId="chat-a" />);
      });
      await settle();
      expect(api.listMessages).toHaveBeenCalledTimes(2);
      const withPrompts = { ...reply, related_prompts: ["More?"] };
      (api.listMessages as jest.Mock).mockResolvedValueOnce({ messages: [hello, answer, saved, withPrompts], has_more: false });
      await act(async () => { setThread((prev) => prev.map((m) => (m.id === reply.id ? withPrompts : m))); });
      await settle();
      // The read the questions landed under is dropped; the one after it holds them.
      await act(async () => { firstRead.resolve({ messages: [hello, answer, saved, reply], has_more: false }); });
      await settle();
      expect(api.listMessages).toHaveBeenCalledTimes(3);
      expect(visibleMessages.map((m) => m.id)).toEqual([uuid(1), uuid(2), uuid(3), uuid(4)]);
      expect(visibleMessages[3].related_prompts).toEqual(["More?"]);
      expect(peekCachedChatPage("chat-a")?.messages[3].related_prompts).toEqual(["More?"]);
    } finally {
      jest.useRealTimers();
    }
  });

  it("merges the page as usual after Stop took back the turn waiting for it", async () => {
    jest.useFakeTimers();
    try {
      const page = deferred<Page>();
      (api.listMessages as jest.Mock).mockReturnValueOnce(page.promise);
      const view = await render(<RouteProbe routeId="chat-a" />);
      const turn = heldTurn();
      let verdict: boolean | undefined;
      await act(async () => {
        setThread((prev) => [...prev, sent, streamingRow]);
        view.rerender(<RouteProbe routeId="chat-a" streaming />);
        void whenOpenedPageSettled("chat-a", turn).then((go) => { verdict = go; });
      });
      // Stop (useChat.stopGeneration): the turn stops waiting, and its bubble and dots go.
      await act(async () => {
        withdrawFromOpenedPage("chat-a", turn);
        setThread((prev) => prev.filter((m) => m.id !== "local-9" && m.id !== "streaming"));
        view.rerender(<RouteProbe routeId="chat-a" />);
      });
      expect(verdict).toBe(false);
      await act(async () => { await jest.advanceTimersByTimeAsync(OPENED_PAGE_WAIT_MS); });
      const elsewhere = [userRow(uuid(3), "From the laptop"), message(uuid(4), "Laptop answer")];
      await act(async () => { page.resolve({ messages: [hello, answer, ...elsewhere], has_more: false }); });
      expect(visibleMessages.map((m) => m.id)).toEqual([uuid(1), uuid(2), uuid(3), uuid(4)]);
      expect(api.listMessages).toHaveBeenCalledTimes(1);
      expect(mockComposer.stashFailedDraftForThread).not.toHaveBeenCalled();
    } finally {
      jest.useRealTimers();
    }
  });

  it("forgets the last open's server read when the chat opens again", async () => {
    const view = await render(<RouteProbe routeId="chat-a" />);
    await waitFor(() => expect(routeState.chatLoading).toBe(false));
    await view.rerender(<RouteProbe routeId={undefined as unknown as string} />);
    const later = Date.now() + 21_000;
    const clock = jest.spyOn(Date, "now").mockReturnValue(later);
    try {
      (api.listMessages as jest.Mock).mockReturnValue(deferred<Page>().promise);
      await view.rerender(<RouteProbe routeId="chat-a" />);
      expect(visibleMessages).toEqual([hello, answer]);
      // A thumbs-up while the read is out: nothing this open read backs the thread yet.
      await act(async () => {
        setThread((prev) => prev.map((m) => (m.id === answer.id ? { ...m, feedback: "up" } : m)));
      });
      expect(isCachedChatPageFresh("chat-a", undefined)).toBe(false);
    } finally {
      clock.mockRestore();
    }
  });

  it("reopens a chat it showed moments ago without reading it again", async () => {
    const view = await openAThenB();
    await view.rerender(<RouteProbe routeId="chat-a" />);
    expect(visibleMessages).toEqual([hello, answer]);
    expect(routeState.chatLoading).toBe(false);
    expect(routeState.chatTitle).toBe("chat-a");
    expect(api.listMessages).not.toHaveBeenCalled();
    expect(readCachedChatMessages).not.toHaveBeenCalled();
  });

  it("reads the chat again when its drawer row changed since", async () => {
    const view = await openAThenB();
    (getCachedChat as jest.Mock).mockImplementation((id: string) =>
      listedChat(id, id === "chat-a" ? "2026-01-02T00:00:00Z" : undefined));
    await view.rerender(<RouteProbe routeId="chat-a" />);
    await waitFor(() => expect(api.listMessages).toHaveBeenCalledWith("token", "chat-a", { limit: 40 }));
  });

  it("reads the chat again after the app was in the background", async () => {
    const view = await openAThenB();
    await act(async () => { for (const handler of [...appStateHandlers]) handler("background"); });
    (api.listMessages as jest.Mock).mockReturnValue(deferred<Page>().promise);
    await view.rerender(<RouteProbe routeId="chat-a" />);
    // Painted from memory at once, and read again.
    expect(visibleMessages).toEqual([hello, answer]);
    expect(routeState.historyPending).toBe(false);
    expect(api.listMessages).toHaveBeenCalledWith("token", "chat-a", { limit: 40 });
    expect(readCachedChatMessages).not.toHaveBeenCalled();
  });

  it("keeps the thread once a turn finishes, so the next open paints it", async () => {
    const view = await render(<RouteProbe routeId="chat-a" />);
    await waitFor(() => expect(routeState.chatLoading).toBe(false));
    expect(isCachedChatPageFresh("chat-a", undefined)).toBe(true);
    await act(async () => {
      setThread((prev) => [...prev, sent, streamingRow]);
      view.rerender(<RouteProbe routeId="chat-a" streaming />);
    });
    expect(isCachedChatPageFresh("chat-a", undefined)).toBe(false);
    const reply = message(uuid(4), "Reply");
    await act(async () => {
      setThread((prev) => [...prev.filter((m) => m.id !== "streaming"), reply]);
      view.rerender(<RouteProbe routeId="chat-a" />);
    });
    expect(peekCachedChatPage("chat-a")?.messages.map((m) => m.id)).toEqual([uuid(1), uuid(2), "local-9", uuid(4)]);
    expect(isCachedChatPageFresh("chat-a", undefined)).toBe(true);
  });

  it("does not redraw the rows the network page left as they were", async () => {
    const page = deferred<Page>();
    (api.listMessages as jest.Mock).mockReturnValue(page.promise);
    renders.clear();
    await render(<ListProbe routeId="chat-a" />);
    expect(Object.fromEntries(renders)).toEqual({ [uuid(1)]: 1, [uuid(2)]: 1 });
    await act(async () => {
      page.resolve({ messages: [{ ...hello }, { ...answer, content: "Hi there, edited" }], has_more: false });
    });
    expect(Object.fromEntries(renders)).toEqual({ [uuid(1)]: 1, [uuid(2)]: 2 });
  });
});
