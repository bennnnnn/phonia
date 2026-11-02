/** A → B → A within the refresh window reads A once (code-health audit NET-16). */
import React, { useState } from "react";
import { Text } from "react-native";
import { act, render, screen, waitFor } from "@testing-library/react-native";

import { useChatRouteLoader } from "@/features/chat/hooks/useChatRouteLoader";
import { api, type Message } from "@/lib/api";
import { clearAllCachedChatMessages } from "@/features/chat/model/messageCache";

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 0 }));
jest.mock("@/features/chat/drawer/drawer", () => ({
  getChatMutationRevision: () => 0,
  subscribeChatChanges: () => () => undefined,
  removeChatGlobal: jest.fn(),
}));
jest.mock("@/lib/api/client", () => ({ ApiRequestError: class extends Error {} }));
jest.mock("expo-router", () => ({ useFocusEffect: () => undefined, useRouter: () => ({}) }));
jest.mock("@/lib/api", () => ({ api: { getChat: jest.fn(), listMessages: jest.fn() } }));
jest.mock("@/features/chat/model/chatListCache", () => {
  const listed = (id: string) => ({ id, title: id.toUpperCase(), pinned: false, archived: false });
  return { getCachedChat: listed, getFetchedChat: listed };
});
// The kept pages are real; the file behind them is not.
jest.mock("expo-file-system/legacy", () => ({ cacheDirectory: null }));
jest.mock("@/features/chat/hooks/useChatTitlePolling", () => ({
  useChatTitlePolling: () => ({ titleGenerating: false, pollForTitle: jest.fn(), handleFirstReply: jest.fn() }),
}));
jest.mock("@/features/chat/hooks/useChatHighlightScroll", () => ({
  useChatHighlightScroll: () => ({ highlightedMessageId: null }),
}));

const draft = {
  draftChatIdRef: { current: null },
  skipLoadForChatIdRef: { current: null },
  creatingRef: { current: false },
  discardEmptyChat: jest.fn(),
  clearDraftChat: jest.fn(),
} as never;
const router = { setParams: jest.fn() } as never;

function Probe({ route, streaming = false }: { route: string; streaming?: boolean }) {
  const [chatId, setChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  useChatRouteLoader({
    token: "token", routeChatId: route, routeHighlightMessage: undefined, router, draft,
    chatId, setChatId, editThread: setMessages, messages, streaming, stopGeneration: jest.fn(),
    listRef: { current: null }, showActionBanner: jest.fn(), t: (key) => key,
  });
  return <Text testID="thread">{messages.map((m) => m.content).join("|")}</Text>;
}

const reply = (chat: string, content: string): Message =>
  ({ id: `0190a000-0000-7000-8000-${chat.padStart(12, "0")}`, role: "assistant", content, model: null, created_at: "t" });
const reads = (chat: string) =>
  jest.mocked(api.listMessages).mock.calls.filter(([, id]) => id === chat).length;

beforeEach(async () => {
  jest.clearAllMocks();
  await clearAllCachedChatMessages();
  jest.mocked(api.listMessages).mockImplementation(async (_token, chat) => ({
    messages: [reply(chat, `${chat} thread`)],
    has_more: false,
  }));
});

it("shows a chat left moments ago as it was, without reading it again", async () => {
  const view = await render(<Probe route="a" />);
  await waitFor(() => expect(screen.getByTestId("thread")).toHaveTextContent("a thread"));
  await act(async () => { await view.rerender(<Probe route="b" />); });
  await waitFor(() => expect(screen.getByTestId("thread")).toHaveTextContent("b thread"));
  await act(async () => { await view.rerender(<Probe route="a" />); });
  await waitFor(() => expect(screen.getByTestId("thread")).toHaveTextContent("a thread"));
  expect(reads("a")).toBe(1);
  expect(reads("b")).toBe(1);
});

it("reads the chat again once the window has passed", async () => {
  const now = Date.now();
  const clock = jest.spyOn(Date, "now").mockReturnValue(now);
  const view = await render(<Probe route="a" />);
  await waitFor(() => expect(reads("a")).toBe(1));
  await act(async () => { await view.rerender(<Probe route="b" />); });
  await waitFor(() => expect(reads("b")).toBe(1));
  clock.mockReturnValue(now + 21_000);
  await act(async () => { await view.rerender(<Probe route="a" />); });
  await waitFor(() => expect(reads("a")).toBe(2));
  clock.mockRestore();
});
