import React from "react";
import { act, render } from "@testing-library/react-native";

import { useLiveTalk } from "@/features/speech/hooks/useLiveTalk";
import { reportRecoverableError } from "@/lib/reportRecoverableError";

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
// The chime's module fails to load (a dev bundle that lost its server, say).
jest.mock("@/features/speech/model/liveTalkSfx", () => {
  throw new Error("chime unavailable");
});
jest.mock("@/features/speech/model/realtimeVoice", () => ({
  createRealtimeVoiceSession: jest.fn(async () => mockSession),
  isRealtimeVoiceAvailable: () => true,
}));
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

it("opens and closes Live Talk although its chime cannot load", async () => {
  await render(<Probe />);
  await act(async () => {
    await live.open();
  });
  expect(live.visible).toBe(true);
  expect(live.phase).toBe("recording");

  await act(async () => {
    live.close();
  });
  expect(live.visible).toBe(false);
  expect(mockSession.close).toHaveBeenCalledTimes(1);
  expect(reportRecoverableError).not.toHaveBeenCalled();
});
