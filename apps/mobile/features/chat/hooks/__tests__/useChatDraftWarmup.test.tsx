import React from "react";
import { Keyboard, Platform } from "react-native";
import { act, render } from "@testing-library/react-native";

import { AccountSessionContext } from "@/contexts/accountSession";
import { ComposerDraftProvider, useComposerDraftApi } from "@/features/chat/context/ComposerDraftContext";
import { useChatDraftWarmup } from "@/features/chat/hooks/useChatDraftWarmup";

type Props = { chatId: string | null; draftChatId?: string | null; streaming?: boolean };

const connect = jest.fn();
let mockFocused = true;
jest.mock("expo-router", () => ({ useNavigation: () => ({ isFocused: () => mockFocused }) }));
const SIGNED_IN = { account: "account-1", getToken: () => "token" };
let setInput: (text: string) => void = () => {};

function Screen({ chatId, draftChatId = null, streaming = false }: Props) {
  useChatDraftWarmup({ chatId, streaming, draftChatId, connect });
  const draft = useComposerDraftApi();
  React.useLayoutEffect(() => { setInput = draft.setInput; });
  return null;
}

describe("useChatDraftWarmup", () => {
  const keyboardListeners = new Map<string, Set<() => void>>();

  beforeEach(() => {
    connect.mockClear();
    mockFocused = true;
    keyboardListeners.clear();
    jest.spyOn(Keyboard, "addListener").mockImplementation(((event: string, listener: () => void) => {
      const listeners = keyboardListeners.get(event) ?? new Set();
      listeners.add(listener);
      keyboardListeners.set(event, listeners);
      return { remove: () => listeners.delete(listener) } as never;
    }) as never);
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  async function renderScreen(props: Props) {
    return act(async () => render(
      <AccountSessionContext.Provider value={SIGNED_IN}>
        <ComposerDraftProvider>
          <Screen {...props} />
        </ComposerDraftProvider>
      </AccountSessionContext.Provider>,
    ));
  }

  const showKeyboard = async () => {
    const event = Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow";
    await act(async () => { for (const listener of keyboardListeners.get(event) ?? []) listener(); });
  };

  it("ignores a keyboard on another screen stacked over the chat", async () => {
    await renderScreen({ chatId: "chat-1" });
    mockFocused = false;
    await showKeyboard();
    expect(connect).not.toHaveBeenCalled();
  });

  it("opens an open chat's socket when the keyboard comes up, each time", async () => {
    await renderScreen({ chatId: "chat-1" });
    expect(connect).not.toHaveBeenCalled();
    await showKeyboard();
    await showKeyboard();
    expect(connect).toHaveBeenCalledTimes(2);
  });

  it("opens the socket on the composer's first character, not on every one", async () => {
    await renderScreen({ chatId: "chat-1" });
    await act(async () => { setInput("h"); });
    await act(async () => { setInput("he"); });
    expect(connect).toHaveBeenCalledTimes(1);
    await act(async () => { setInput(""); });
    await act(async () => { setInput("n"); });
    expect(connect).toHaveBeenCalledTimes(2);
  });

  it("warms a draft chat's socket as soon as the draft exists", async () => {
    await renderScreen({ chatId: null, draftChatId: "draft-1" });
    expect(connect).toHaveBeenCalledTimes(1);
  });

  it("stops listening for the keyboard once the screen is gone", async () => {
    const view = await renderScreen({ chatId: "chat-1" });
    await act(async () => { view.unmount(); });
    await showKeyboard();
    expect(connect).not.toHaveBeenCalled();
  });
});
