import React from "react";
import { BackHandler, Linking } from "react-native";
import { act, render } from "@testing-library/react-native";

import { useLiveTalk } from "@/features/speech/hooks/useLiveTalk";
import { api } from "@/lib/api";
import { ApiRequestError } from "@/lib/api/errorBody";
import { createRealtimeVoiceSession } from "@/features/speech/model/realtimeVoice";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { confirmDialog } from "@/ui/overlay/dialogs";

let mockDrawerOpen = false;
const mockDrawerControls = { open: jest.fn(), close: jest.fn(), isOpenNow: () => mockDrawerOpen };
jest.mock("@/contexts/DrawerContext", () => ({ useDrawerControls: () => mockDrawerControls }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/lib/reportRecoverableError", () => ({ reportRecoverableError: jest.fn() }));
jest.mock("@/ui/overlay/dialogs", () => ({ confirmDialog: jest.fn(async () => true) }));
jest.mock("@/features/speech/model/liveTalkSfx", () => ({ playLiveTalkCue: jest.fn(async () => undefined) }));
jest.mock("@/features/speech/model/realtimeVoice", () => ({
  createRealtimeVoiceSession: jest.fn(),
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
const onUpgrade = jest.fn();

function Probe() {
  const value = useLiveTalk({
    token: "tok",
    chatId: "chat-1",
    ensureChatId: async () => "chat-1",
    editThread: jest.fn(),
    isOffline: false,
    onUpgrade,
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

/** Open a call; returns what the realtime session says to the hook. */
async function openCall(): Promise<(event: { type: string; [key: string]: unknown }) => void> {
  let emit!: (event: { type: string; [key: string]: unknown }) => void;
  (createRealtimeVoiceSession as jest.Mock).mockImplementationOnce(async ({ onEvent }) => {
    emit = onEvent;
    return { callId: "call-1", maxDurationSeconds: 600, setMuted: jest.fn(), cancelResponse: jest.fn(), close: jest.fn() };
  });
  await render(<Probe />);
  await act(async () => {
    await live.open();
  });
  expect(live.visible).toBe(true);
  return emit;
}

describe("useLiveTalk microphone denial (F8.8)", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("asks for the microphone with Open Settings instead of the generic unavailable", async () => {
    const openSettings = jest.spyOn(Linking, "openSettings").mockResolvedValue(undefined);
    (createRealtimeVoiceSession as jest.Mock).mockRejectedValueOnce({
      name: "SecurityError",
      message: "Permission denied.",
    });
    await render(<Probe />);
    await act(async () => {
      await live.open();
    });

    expect(confirmDialog).toHaveBeenCalledWith({
      title: "chat.live_talk_mic_permission_title",
      message: "chat.live_talk_mic_permission_body",
      cancelLabel: "common.cancel",
      confirmLabel: "chat.location_open_settings",
    });
    expect(reportRecoverableError).not.toHaveBeenCalled();
    expect(openSettings).toHaveBeenCalledTimes(1);
    expect(live.visible).toBe(false);
    openSettings.mockRestore();
  });

  it("still says unavailable when WebRTC itself is missing", async () => {
    (createRealtimeVoiceSession as jest.Mock).mockRejectedValueOnce(new Error("webrtc_unavailable"));
    await render(<Probe />);
    await act(async () => {
      await live.open();
    });

    expect(confirmDialog).not.toHaveBeenCalled();
    expect(reportRecoverableError).toHaveBeenCalledWith(null, "chat.live_talk_unavailable_body");
  });

  // A microphone that gave no audio said "update the app", as a build without WebRTC does.
  it("says the microphone, not the app, when the microphone gave no audio", async () => {
    (createRealtimeVoiceSession as jest.Mock).mockRejectedValueOnce(new Error("microphone_unavailable"));
    await render(<Probe />);
    await act(async () => {
      await live.open();
    });

    expect(confirmDialog).not.toHaveBeenCalled();
    expect(jest.mocked(reportRecoverableError).mock.calls).toEqual([[null, "chat.live_talk_mic_unavailable"]]);
    expect(live.visible).toBe(false);
  });

  // Every 503 said "Live talk isn't set up on this server yet", a Redis outage included.
  it.each([
    [{ code: "unavailable", message: "Service temporarily unavailable. Please retry shortly." }, "common.service_unavailable"],
    [{ code: "not_configured", message: "Realtime voice is not configured" }, "chat.live_talk_not_configured"],
  ])("words a 503 by its code: %j", async (detail, line) => {
    jest.mocked(api.liveTalkStatus).mockRejectedValueOnce(new ApiRequestError(503, JSON.stringify({ detail })));
    await render(<Probe />);
    await act(async () => {
      await live.open();
    });

    expect(reportRecoverableError).toHaveBeenCalledWith(null, line);
    expect(createRealtimeVoiceSession).not.toHaveBeenCalled();
  });

  // Every 429 said "You've used this month's live talk minutes"; a 502 from the
  // realtime provider said "Update the app".
  it.each([
    [429, { code: "live_talk_minutes_used", message: "You've used this month's live talk minutes." }, "chat.live_talk_limit_body"],
    [429, { code: "speech_rate_limited", message: "Too many live talk requests." }, "chat.live_talk_rate_limited"],
    [429, { code: "voice_spend_cap", message: "Voice is temporarily unavailable." }, "chat.live_talk_paused"],
    [502, { code: "upstream_failed", message: "Could not start realtime voice" }, "chat.live_talk_connect_failed"],
  ])("words a refused start (%i) by its code: %j", async (status, detail, line) => {
    (createRealtimeVoiceSession as jest.Mock).mockRejectedValueOnce(
      new ApiRequestError(status, JSON.stringify({ detail })),
    );
    await render(<Probe />);
    await act(async () => {
      await live.open();
    });

    expect(reportRecoverableError).toHaveBeenCalledWith(null, line);
    expect(live.visible).toBe(false);
  });

  // Every 403 opened the paywall: consent_required did too, on top of the consent step
  // the API client opens for it.
  it.each([
    [{ code: "not_in_plan", message: "Live talk isn't part of your plan." }, 1],
    [{ code: "consent_required", message: "Agree to how Recall uses outside AI services to continue." }, 0],
  ])("opens the paywall only for not_in_plan: %j", async (detail, paywalls) => {
    (createRealtimeVoiceSession as jest.Mock).mockRejectedValueOnce(
      new ApiRequestError(403, JSON.stringify({ detail })),
    );
    await render(<Probe />);
    await act(async () => {
      await live.open();
    });

    expect(onUpgrade).toHaveBeenCalledTimes(paywalls);
    expect(reportRecoverableError).not.toHaveBeenCalled();
    expect(live.visible).toBe(false);
  });

  it("words the API's own request limit, which names no code, as too many attempts", async () => {
    jest.mocked(api.liveTalkStatus).mockRejectedValueOnce(
      new ApiRequestError(429, JSON.stringify({ detail: "Too many requests. Please slow down." })),
    );
    await render(<Probe />);
    await act(async () => {
      await live.open();
    });

    expect(reportRecoverableError).toHaveBeenCalledWith(null, "chat.live_talk_rate_limited");
    expect(createRealtimeVoiceSession).not.toHaveBeenCalled();
  });

  it("says live talk is off, not that the app is old, when the server switched it off", async () => {
    jest.mocked(api.liveTalkStatus).mockResolvedValueOnce({ enabled: false, entitled: false, remaining: 0, limit: 0 });
    await render(<Probe />);
    await act(async () => {
      await live.open();
    });

    expect(reportRecoverableError).toHaveBeenCalledWith(null, "chat.live_talk_off");
    expect(createRealtimeVoiceSession).not.toHaveBeenCalled();
  });

  // A save never gets `live_talk_minutes_used`, yet each of its 429s said the month was used.
  it.each([
    [{ code: "rate_limited", message: "Too many live talk requests." }, "chat.live_talk_rate_limited"],
    [{ code: "voice_spend_cap", message: "Voice is temporarily unavailable." }, "chat.live_talk_paused"],
    [{ code: "live_talk_saves_used", message: "This live talk call can't save more turns." }, "chat.live_talk_saves_used"],
  ])("ends the call on a refused save in its own words: %j", async (detail, line) => {
    let emit!: (event: { type: string; [key: string]: unknown }) => void;
    (createRealtimeVoiceSession as jest.Mock).mockImplementationOnce(async ({ onEvent }) => {
      emit = onEvent;
      return { callId: "call-1", maxDurationSeconds: 600, setMuted: jest.fn(), cancelResponse: jest.fn(), close: jest.fn() };
    });
    jest.mocked(api.persistRealtimeLiveTalkTurn).mockRejectedValueOnce(
      new ApiRequestError(429, JSON.stringify({ detail })),
    );
    await render(<Probe />);
    await act(async () => {
      await live.open();
    });
    expect(live.visible).toBe(true);

    await act(async () => {
      emit({ type: "speech_started", turnId: "turn-1" });
      emit({ type: "user_transcript", text: "hello" });
      // The next utterance saves the last one.
      emit({ type: "speech_started", turnId: "turn-2" });
    });

    expect(api.persistRealtimeLiveTalkTurn).toHaveBeenCalledTimes(1);
    expect(reportRecoverableError).toHaveBeenCalledWith(null, line);
    expect(reportRecoverableError).not.toHaveBeenCalledWith(null, "chat.live_talk_limit_body");
    expect(live.visible).toBe(false);
  });

  // A save the plan or the session no longer allowed showed the server's English
  // ("Realtime session is not active") and left the call, and the provider, running.
  it.each([
    [{ code: "not_in_plan", message: "Live talk isn't part of your plan." }, null],
    [{ code: "live_talk_session_ended", message: "Realtime session is not active" }, "chat.live_talk_session_ended"],
  ])("ends the call once on a save the plan or session no longer allows: %j", async (detail, line) => {
    const emit = await openCall();
    jest.mocked(api.persistRealtimeLiveTalkTurn).mockRejectedValue(
      new ApiRequestError(403, JSON.stringify({ detail })),
    );

    await act(async () => {
      emit({ type: "speech_started", turnId: "turn-1" });
      emit({ type: "user_transcript", text: "hello" });
      emit({ type: "speech_started", turnId: "turn-2" });
      // Heard before the refusal lands: the hang-up saves it, and is refused the same way.
      emit({ type: "user_transcript", text: "are you there" });
    });

    expect(api.persistRealtimeLiveTalkTurn).toHaveBeenCalledTimes(2);
    expect(live.visible).toBe(false);
    expect(onUpgrade).toHaveBeenCalledTimes(line ? 0 : 1);
    expect(jest.mocked(reportRecoverableError).mock.calls).toEqual(line ? [[null, line]] : []);
    jest.mocked(api.persistRealtimeLiveTalkTurn).mockReset();
  });

  it.each([
    [new ApiRequestError(404, JSON.stringify({ detail: { code: "not_found", message: "Chat not found" } })),
      "chat.live_talk_save_failed"],
    [new ApiRequestError(500, "Internal Server Error"), "chat.live_talk_save_failed"],
    [new ApiRequestError(503, JSON.stringify({ detail: { code: "unavailable", message: "Service temporarily unavailable." } })),
      "common.service_unavailable"],
  ])("words any other refused save in the phone's language, and keeps the call: %s", async (error, line) => {
    const emit = await openCall();
    jest.mocked(api.persistRealtimeLiveTalkTurn).mockRejectedValueOnce(error);

    await act(async () => {
      emit({ type: "speech_started", turnId: "turn-1" });
      emit({ type: "user_transcript", text: "hello" });
      emit({ type: "speech_started", turnId: "turn-2" });
    });

    expect(reportRecoverableError).toHaveBeenCalledWith(null, line);
    expect(live.visible).toBe(true);
  });

  // Both showed the provider's English.
  it.each([
    [{ type: "error", message: "Realtime voice data channel failed", fatal: true }, "chat.live_talk_connect_failed", false],
    [{ type: "error", message: "Conversation already has an active response" }, "chat.error_generic", true],
  ])("words an error during a call in the phone's language: %j", async (event, line, stillOpen) => {
    const emit = await openCall();

    await act(async () => {
      emit(event);
    });

    expect(jest.mocked(reportRecoverableError).mock.calls).toEqual([[null, line]]);
    expect(live.visible).toBe(stillOpen);
  });

  it("leaves Back to an open drawer, reading the drawer when Back is pressed", async () => {
    const backHandlers: (() => boolean | null | undefined)[] = [];
    const addListener = jest
      .spyOn(BackHandler, "addEventListener")
      .mockImplementation((_event, handler) => {
        backHandlers.push(() => handler({} as never));
        return { remove: jest.fn() };
      });
    (createRealtimeVoiceSession as jest.Mock).mockResolvedValueOnce({
      callId: null,
      maxDurationSeconds: null,
      setMuted: jest.fn(),
      cancelResponse: jest.fn(),
      close: jest.fn(),
    });
    await render(<Probe />);
    await act(async () => {
      await live.open();
    });
    expect(live.visible).toBe(true);
    const back = backHandlers.at(-1)!;

    // The drawer opened after Live Talk did: Back closes the drawer, not Live Talk.
    mockDrawerOpen = true;
    expect(back()).toBe(false);
    expect(live.visible).toBe(true);

    mockDrawerOpen = false;
    await act(async () => {
      expect(back()).toBe(true);
    });
    expect(live.visible).toBe(false);
    addListener.mockRestore();
  });
});
