import {
  deletedIncludesActiveChat,
  getActiveChatIdGlobal,
  registerNewChat,
  setActiveChatIdGlobal,
  startNewChatGlobal,
} from "@/features/chat/drawer/drawer";

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 0 }));

describe("deletedIncludesActiveChat", () => {
  it("returns false when nothing is open", () => {
    expect(deletedIncludesActiveChat(["a", "b"], null)).toBe(false);
    expect(deletedIncludesActiveChat(["a"])).toBe(false);
  });

  it("returns true when the open chat is in the delete batch", () => {
    expect(deletedIncludesActiveChat(["a", "b"], "b")).toBe(true);
  });

  it("returns false when the open chat was not deleted", () => {
    expect(deletedIncludesActiveChat(["a"], "b")).toBe(false);
  });

  it("reads the registered active chat id by default", () => {
    const unregister = setActiveChatIdGlobal("open-1");
    try {
      expect(getActiveChatIdGlobal()).toBe("open-1");
      expect(deletedIncludesActiveChat(["open-1", "other"])).toBe(true);
      expect(deletedIncludesActiveChat(["other"])).toBe(false);
    } finally {
      unregister();
    }
    expect(getActiveChatIdGlobal()).toBeNull();
  });
});

describe("registerNewChat", () => {
  it("clears the handler on unregister so a dead screen cannot create orphan drafts", () => {
    const fn = jest.fn();
    const unregister = registerNewChat(fn);
    startNewChatGlobal({ force: true });
    expect(fn).toHaveBeenCalledWith({ force: true });
    unregister();
    startNewChatGlobal({ force: true });
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("stacked screens: popping the top instance restores the one underneath", () => {
    // Library pushes a second copy of the chat route; when it unmounts, its
    // cleanup must not clear the still-mounted home screen's registration.
    const home = jest.fn();
    const pushed = jest.fn();
    const unregisterHome = registerNewChat(home);
    const unregisterPushed = registerNewChat(pushed);

    startNewChatGlobal();
    expect(pushed).toHaveBeenCalledTimes(1);
    expect(home).not.toHaveBeenCalled();

    unregisterPushed();
    startNewChatGlobal();
    expect(home).toHaveBeenCalledTimes(1);

    // Double-unregister is a safe no-op.
    unregisterPushed();
    startNewChatGlobal();
    expect(home).toHaveBeenCalledTimes(2);

    unregisterHome();
    startNewChatGlobal();
    expect(home).toHaveBeenCalledTimes(2);
  });

  it("stacked active chat ids: popping the top instance restores the underlying chat", () => {
    const unregisterHome = setActiveChatIdGlobal("home-chat");
    const unregisterPushed = setActiveChatIdGlobal("library-chat");
    expect(getActiveChatIdGlobal()).toBe("library-chat");
    unregisterPushed();
    expect(getActiveChatIdGlobal()).toBe("home-chat");
    unregisterHome();
    expect(getActiveChatIdGlobal()).toBeNull();
  });
});
