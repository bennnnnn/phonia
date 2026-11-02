import React from "react";
import { AppState, Text } from "react-native";
import { act, render, screen, waitFor } from "@testing-library/react-native";

import { useDraftChat } from "@/features/chat/hooks/useDraftChat";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    createChat: jest.fn(),
    deleteChat: jest.fn(async () => undefined),
    deleteChatIfEmpty: jest.fn(async () => undefined),
  },
}));
jest.mock("@/features/chat/model/chatListCache", () => ({
  rememberCreatedChat: jest.fn(),
}));
// One object, as the provider keeps it.
const mockAccountSession = { account: "user-1:0", getToken: () => "token" };
jest.mock("@/contexts/accountSession", () => ({
  useAccountSession: () => mockAccountSession,
}));

function Probe({ chatId = null, intent = false }: { chatId?: string | null; intent?: boolean }) {
  const draft = useDraftChat({ chatId, intent });
  return <Text testID="draft-id">{draft.draftChatId ?? "none"}</Text>;
}

let appStateListener: ((state: string) => void) | null = null;

describe("useDraftChat (code-health audit NET-13)", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.createChat as jest.Mock).mockResolvedValue({ id: "draft-1" });
    jest.spyOn(AppState, "addEventListener").mockImplementation((_type, listener) => {
      appStateListener = listener as (state: string) => void;
      return { remove: jest.fn() } as unknown as ReturnType<typeof AppState.addEventListener>;
    });
  });

  it("makes no chat when a new chat is only looked at", async () => {
    await render(<Probe />);
    await act(async () => {});
    expect(api.createChat).not.toHaveBeenCalled();
  });

  it("makes the chat on the first keystroke, before the Send tap", async () => {
    const view = await render(<Probe />);
    await view.rerender(<Probe intent />);
    await waitFor(() => {
      expect(screen.getByTestId("draft-id").props.children).toBe("draft-1");
    });
    expect(api.createChat).toHaveBeenCalledTimes(1);
    expect(api.createChat).toHaveBeenCalledWith("token", "auto");
  });

  it("does not create a competing draft while an existing chat is opening", async () => {
    await render(<Probe chatId="existing-1" intent />);
    await act(async () => {});
    expect(api.createChat).not.toHaveBeenCalled();
  });

  it("drops an unused draft once on background, and keeps it while inactive", async () => {
    const view = await render(<Probe intent />);
    await waitFor(() => expect(screen.getByTestId("draft-id").props.children).toBe("draft-1"));
    // The text was sent or cleared: nothing is being written any more.
    await view.rerender(<Probe />);
    await act(async () => { appStateListener?.("inactive"); });
    expect(api.deleteChatIfEmpty).not.toHaveBeenCalled();
    await act(async () => { appStateListener?.("background"); });
    expect(api.deleteChatIfEmpty).toHaveBeenCalledTimes(1);
    expect(api.deleteChatIfEmpty).toHaveBeenCalledWith("token", "draft-1");
    expect(api.deleteChat).not.toHaveBeenCalled();
  });

  it("keeps the draft through background while the user is still writing", async () => {
    await render(<Probe intent />);
    await waitFor(() => expect(screen.getByTestId("draft-id").props.children).toBe("draft-1"));
    await act(async () => { appStateListener?.("background"); });
    expect(api.deleteChatIfEmpty).not.toHaveBeenCalled();
  });
});
