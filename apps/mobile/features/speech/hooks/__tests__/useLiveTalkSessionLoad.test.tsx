import React from "react";
import { act, render } from "@testing-library/react-native";

import { useLiveTalk } from "@/features/speech/hooks/useLiveTalk";

const mockModuleLoads: string[] = [];
const mockCues: string[] = [];
const mockSession = {
  callId: "call-1",
  maxDurationSeconds: 600,
  setMuted: jest.fn(),
  cancelResponse: jest.fn(),
  close: jest.fn(),
};

jest.mock("@/contexts/DrawerContext", () => ({
  useDrawerControls: () => ({ open: jest.fn(), close: jest.fn(), isOpenNow: () => false }),
}));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/lib/reportRecoverableError", () => ({ reportRecoverableError: jest.fn() }));
jest.mock("@/ui/overlay/dialogs", () => ({ confirmDialog: jest.fn(async () => true) }));
jest.mock("@/features/speech/model/liveTalkSfx", () => {
  mockModuleLoads.push("cues");
  return {
    playLiveTalkCue: jest.fn(async (kind: string) => {
      mockCues.push(kind);
    }),
  };
});
jest.mock("@/features/speech/model/realtimeVoice", () => {
  mockModuleLoads.push("realtime voice");
  return {
    createRealtimeVoiceSession: jest.fn(async () => mockSession),
    isRealtimeVoiceAvailable: () => true,
  };
});
jest.mock("@/lib/api", () => ({
  api: {
    liveTalkStatus: jest.fn(async () => ({
      enabled: true,
      entitled: true,
      remaining: 30,
      limit: 60,
      remaining_seconds: 1800,
      min_session_seconds: 60,
    })),
    endRealtimeSession: jest.fn(async () => ({})),
    persistRealtimeLiveTalkTurn: jest.fn(),
  },
}));

let live!: ReturnType<typeof useLiveTalk>;

function Probe() {
  const value = useLiveTalk({
    token: "tok",
    chatId: "chat-1",
    ensureChatId: async () => "chat-1",
    editThread: jest.fn(),
    isOffline: false,
    onUpgrade: jest.fn(),
    onScrollToLatest: jest.fn(),
    newMessageCountRef: { current: 0 },
    onFirstReply: jest.fn(),
    t: (key: string) => key,
  });
  React.useLayoutEffect(() => {
    live = value;
  });
  return null;
}

describe("useLiveTalk session loading", () => {
  it("loads the realtime session and its chimes when Live Talk starts, not with the chat", async () => {
    await render(<Probe />);
    expect(mockModuleLoads).toEqual([]);
    expect(live.visible).toBe(false);

    await act(async () => {
      await live.open();
    });
    expect(mockModuleLoads.sort()).toEqual(["cues", "realtime voice"]);
    expect(live.visible).toBe(true);
    expect(live.phase).toBe("recording");
    expect(mockCues).toEqual(["start"]);

    await act(async () => {
      live.close();
    });
    expect(mockSession.close).toHaveBeenCalledTimes(1);
    expect(mockCues).toEqual(["start", "end"]);
    expect(live.visible).toBe(false);
  });
});
