import React, { useState } from "react";
import { Text } from "react-native";
import { act, render, waitFor } from "@testing-library/react-native";

import { useChatTitlePolling } from "@/features/chat/hooks/useChatTitlePolling";

let mockSession = 0;
let mockRevision = 0;
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));

jest.mock("@/lib/api", () => ({
  api: {
    getChat: jest.fn(),
  },
}));

jest.mock("@/features/chat/model/chatListCache", () => ({
  getCachedChat: jest.fn(),
  peekCreatedChat: jest.fn(),
}));

jest.mock("@/features/chat/drawer/drawer", () => {
  let pending: string | null = null;
  return {
    getChatMutationRevision: () => mockRevision,
    insertChatGlobal: jest.fn(),
    patchChatGlobal: jest.fn(),
    setChatTitleGenerating: jest.fn((id: string | null) => {
      pending = id;
    }),
    isChatTitleGenerating: jest.fn((id: string) => pending === id),
  };
});

import { api } from "@/lib/api";
import { getCachedChat, peekCreatedChat } from "@/features/chat/model/chatListCache";
import { insertChatGlobal, patchChatGlobal, setChatTitleGenerating } from "@/features/chat/drawer/drawer";

const getChat = api.getChat as jest.Mock;
const peekCreated = peekCreatedChat as jest.Mock;
const listedChat = getCachedChat as jest.Mock;
const insertChat = insertChatGlobal as jest.Mock;
const patchChat = patchChatGlobal as jest.Mock;
const setGenerating = setChatTitleGenerating as jest.Mock;

type Polling = ReturnType<typeof useChatTitlePolling>;
let current: Polling;
let screenTitle: string | null = null;

function Probe({
  chatId,
  getFirstUserText,
}: {
  chatId: string | null;
  getFirstUserText?: () => string | undefined;
}) {
  const [title, setTitle] = useState<string | null>(null);
  const result = useChatTitlePolling({
    token: "tok",
    chatId,
    setChatTitle: setTitle,
    getFirstUserText,
  });
  React.useLayoutEffect(() => {
    screenTitle = title;
    current = result;
  }, [title, result]);
  return <Text>{title ?? "none"}</Text>;
}

describe("useChatTitlePolling", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    screenTitle = null;
    mockSession = 0;
    mockRevision = 0;
    setGenerating(null);
    peekCreated.mockReturnValue(undefined);
    listedChat.mockReturnValue(undefined);
    getChat.mockResolvedValue({ title: "A's title" });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("does not apply a title from chat A to chat B's header", async () => {
    const view = await act(async () => render(<Probe chatId="chat-a" />));
    await act(async () => {
      void current.pollForTitle("tok", "chat-a");
    });

    await act(async () => {
      view.rerender(<Probe chatId="chat-b" />);
    });

    await act(async () => {
      jest.advanceTimersByTime(2000);
    });
    await waitFor(() => {
      expect(getChat).toHaveBeenCalledWith("tok", "chat-a");
    });

    expect(screenTitle).toBeNull();
    expect(patchChat).toHaveBeenCalledWith("chat-a", { title: "A's title" });
  });

  it("drops an in-flight title once the screen has moved to another chat", async () => {
    let resolveGet: (value: { title: string }) => void = () => {};
    getChat.mockImplementation(
      () =>
        new Promise<{ title: string }>((resolve) => {
          resolveGet = resolve;
        }),
    );

    const view = await act(async () => render(<Probe chatId="chat-a" />));
    await act(async () => {
      void current.pollForTitle("tok", "chat-a");
    });

    await act(async () => {
      jest.advanceTimersByTime(2000);
    });
    await waitFor(() => {
      expect(getChat).toHaveBeenCalledWith("tok", "chat-a");
    });

    await act(async () => {
      view.rerender(<Probe chatId="chat-b" />);
    });

    await act(async () => {
      resolveGet({ title: "A's title" });
    });

    expect(screenTitle).toBeNull();
    expect(patchChat).toHaveBeenCalledWith("chat-a", { title: "A's title" });
  });

  it("does not stamp the first user line; polls GET /chats/{id} for the topic", async () => {
    const created = {
      id: "chat-a",
      title: null,
      model: "free-chat",
      pinned: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    peekCreated.mockReturnValue(created);
    getChat.mockResolvedValue({ title: "Tonight's leftovers" });

    await act(async () => {
      render(
        <Probe
          chatId="chat-a"
          getFirstUserText={() => "What's still open for me to finish tonight?"}
        />,
      );
    });
    await act(async () => {
      void current.handleFirstReply();
    });

    expect(insertChat).toHaveBeenCalledWith(created);
    expect(screenTitle).toBeNull();

    await act(async () => {
      jest.advanceTimersByTime(2000);
    });
    await waitFor(() => {
      expect(getChat).toHaveBeenCalledWith("tok", "chat-a");
    });
    expect(patchChat).toHaveBeenCalledWith("chat-a", { title: "Tonight's leftovers" });
    expect(screenTitle).toBe("Tonight's leftovers");
  });

  it("inserts the POST /chats row immediately, then polls for the topic", async () => {
    const created = {
      id: "chat-a",
      title: null,
      model: "free-chat",
      pinned: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    peekCreated.mockReturnValue(created);
    getChat.mockResolvedValue({ title: "Greeting" });

    await act(async () => {
      render(<Probe chatId="chat-a" />);
    });
    await act(async () => {
      void current.handleFirstReply();
    });

    expect(insertChat).toHaveBeenCalledWith(created);
    expect(getChat).not.toHaveBeenCalled();

    await act(async () => {
      jest.advanceTimersByTime(2000);
    });
    await waitFor(() => {
      expect(getChat).toHaveBeenCalledWith("tok", "chat-a");
    });
    expect(patchChat).toHaveBeenCalledWith("chat-a", { title: "Greeting" });
    expect(screenTitle).toBe("Greeting");
  });

  it("uses Image for an attachment-only first send, then polls for the topic", async () => {
    const created = {
      id: "chat-a",
      title: null,
      model: "free-chat",
      pinned: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    peekCreated.mockReturnValue(created);

    await act(async () => {
      render(
        <Probe
          chatId="chat-a"
          getFirstUserText={() =>
            "[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]"
          }
        />,
      );
    });
    await act(async () => {
      void current.handleFirstReply();
    });

    expect(insertChat).toHaveBeenCalledWith({ ...created, title: "Image" });
    expect(screenTitle).toBe("Image");

    getChat.mockResolvedValue({ title: "Homework photo" });
    await act(async () => {
      jest.advanceTimersByTime(2000);
    });
    await waitFor(() => {
      expect(getChat).toHaveBeenCalledWith("tok", "chat-a");
    });
    expect(patchChat).toHaveBeenCalledWith("chat-a", { title: "Homework photo" });
    expect(screenTitle).toBe("Homework photo");
  });

  it("does not GET or poll when the drawer row already has a title", async () => {
    listedChat.mockReturnValue({
      id: "chat-a",
      title: "Homework",
      model: "free-chat",
      pinned: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    await act(async () => {
      render(<Probe chatId="chat-a" />);
    });
    await act(async () => {
      await current.handleFirstReply();
    });

    expect(getChat).not.toHaveBeenCalled();
    expect(screenTitle).toBe("Homework");

    await act(async () => {
      jest.advanceTimersByTime(10000);
    });
    expect(getChat).not.toHaveBeenCalled();
  });

  it("polls an explicit chat id before React state has caught up", async () => {
    const created = {
      id: "chat-new",
      title: null,
      model: "free-chat",
      pinned: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    peekCreated.mockImplementation((id: string) => (id === "chat-new" ? created : undefined));
    getChat.mockResolvedValue({ title: "Voice note" });

    await act(async () => {
      render(<Probe chatId={null} />);
    });
    await act(async () => {
      void current.handleFirstReply("chat-new");
    });

    expect(insertChat).toHaveBeenCalledWith(created);

    await act(async () => {
      jest.advanceTimersByTime(2000);
    });
    await waitFor(() => {
      expect(getChat).toHaveBeenCalledWith("tok", "chat-new");
    });
    expect(patchChat).toHaveBeenCalledWith("chat-new", { title: "Voice note" });
  });
  it("does not apply a first-reply lookup to a different header", async () => {
    let resolve!: (value: { id: string; title: string }) => void;
    getChat.mockReturnValue(new Promise((done) => { resolve = done; }));
    const view = await render(<Probe chatId="chat-a" />);
    let pending!: Promise<void>;
    await act(async () => { pending = current.handleFirstReply(); });
    await view.rerender(<Probe chatId="chat-b" />);
    await act(async () => {
      resolve({ id: "chat-a", title: "A only" });
      await pending;
    });
    expect(screenTitle).toBeNull();
    expect(insertChat).toHaveBeenCalledWith({ id: "chat-a", title: "A only" });
  });

  it.each(["rename", "logout", "unmount", "return"])('ignores a pending title after %s', async (change) => {
    let resolve!: (value: { title: string }) => void;
    getChat.mockReturnValue(new Promise((done) => { resolve = done; }));
    const view = await render(<Probe chatId="chat-a" />);
    let pending!: Promise<void>;
    await act(async () => { pending = current.pollForTitle("tok", "chat-a"); });
    await act(async () => { jest.advanceTimersByTime(2000); });
    if (change === "rename") mockRevision++;
    if (change === "logout") mockSession++;
    if (change === "unmount") await view.unmount();
    if (change === "return") {
      await view.rerender(<Probe chatId="chat-b" />);
      await view.rerender(<Probe chatId="chat-a" />);
    }
    await act(async () => {
      resolve({ title: "Old title" });
      await pending;
    });
    expect(screenTitle).toBeNull();
    if (change !== "return") expect(patchChat).not.toHaveBeenCalled();
  });

  it("keeps a manual rename made while a poll timer was waiting", async () => {
    await render(<Probe chatId="chat-a" />);
    let pending!: Promise<void>;
    await act(async () => { pending = current.pollForTitle("tok", "chat-a"); });
    mockRevision++;
    listedChat.mockReturnValue({ id: "chat-a", title: "My manual title" });
    await act(async () => { jest.advanceTimersByTime(2000); await pending; });
    expect(getChat).not.toHaveBeenCalled();
    expect(patchChat).not.toHaveBeenCalled();
  });

  it("rejects retained title callbacks from an ended account session", async () => {
    const view = await render(<Probe chatId="chat-a" />);
    const stale = current;
    mockSession++;
    await view.rerender(<Probe chatId="chat-b" />);
    setGenerating.mockClear();
    await act(async () => {
      await stale.pollForTitle("tok", "chat-a");
      await stale.handleFirstReply();
    });
    expect(setGenerating).not.toHaveBeenCalled();
    expect(getChat).not.toHaveBeenCalled();
    expect(insertChat).not.toHaveBeenCalled();
  });

  it("does not schedule network work after unmount", async () => {
    const view = await render(<Probe chatId="chat-a" />);
    let pending!: Promise<void>;
    await act(async () => { pending = current.pollForTitle("tok", "chat-a"); });
    await view.unmount();
    await act(async () => { await pending; });
    await act(async () => { jest.advanceTimersByTime(2000); });
    expect(getChat).not.toHaveBeenCalled();
  });

  it("treats a persisted short manual title as finished", async () => {
    listedChat.mockReturnValue({ id: "chat-a", title: "Chat", pinned: false });
    await render(<Probe chatId="chat-a" />);
    await act(async () => { void current.handleFirstReply(); });
    expect(screenTitle).toBe("Chat");
    expect(setGenerating).not.toHaveBeenCalledWith("chat-a");
    await act(async () => { jest.advanceTimersByTime(2000); });
    expect(getChat).not.toHaveBeenCalled();
  });

});
