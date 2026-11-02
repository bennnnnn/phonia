import React from "react";
import { Linking } from "react-native";
import { act, render } from "@testing-library/react-native";

import { transcribeSpeech } from "@/lib/api";
import { deleteVoiceRecording, startVoiceRecording, type VoiceRecorder } from "@/lib/speech/voiceAudio";
import { useVoiceInput } from "@/features/speech/hooks/useVoiceInput";

jest.mock("@/lib/api", () => ({ transcribeSpeech: jest.fn() }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/lib/reportRecoverableError", () => ({ reportRecoverableError: jest.fn() }));
jest.mock("@/ui/overlay/dialogs", () => ({ confirmDialog: jest.fn(async () => false) }));
jest.mock("@/lib/speech/voiceAudio", () => ({
  VOICE_MAX_RECORDING_MS: 45_000,
  isVoiceInputAvailable: () => true,
  loadExpoAudio: () => ({}),
  requestVoicePermission: jest.fn(async () => ({ granted: true })),
  startVoiceRecording: jest.fn(),
  deleteVoiceRecording: jest.fn(async () => undefined),
}));

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };
function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function fakeRecorder() {
  return {
    stop: jest.fn(async () => "file:///rec.m4a"),
    subscribeMetering: jest.fn(() => () => {}),
  } satisfies VoiceRecorder;
}

let voice: ReturnType<typeof useVoiceInput>;
function Probe() {
  const value = useVoiceInput({ token: "tok", onTranscript: jest.fn(), t: (key) => key });
  React.useLayoutEffect(() => { voice = value; });
  return null;
}

const startMock = startVoiceRecording as jest.MockedFunction<typeof startVoiceRecording>;

describe("useVoiceInput microphone ownership", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
  });
  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
  });

  it("stops a recorder that finishes starting after the screen has gone", async () => {
    const pending = deferred<VoiceRecorder | null>();
    startMock.mockReturnValueOnce(pending.promise);
    const view = await render(<Probe />);
    let started!: Promise<boolean>;
    await act(async () => { started = voice.startRecording(); });
    await view.unmount();

    const recorder = fakeRecorder();
    await act(async () => { pending.resolve(recorder); });
    expect(await started).toBe(false);
    // Nobody is left to stop it: the mic must not keep recording.
    expect(recorder.stop).toHaveBeenCalledTimes(1);
    await act(async () => { jest.advanceTimersByTime(60_000); });
    expect(transcribeSpeech).not.toHaveBeenCalled();
  });

  it("stops a recorder that finishes starting after the user cancelled", async () => {
    const pending = deferred<VoiceRecorder | null>();
    startMock.mockReturnValueOnce(pending.promise);
    await render(<Probe />);
    let started!: Promise<boolean>;
    await act(async () => { started = voice.startRecording(); });
    await act(async () => { voice.cancelVoiceInput(); });

    const recorder = fakeRecorder();
    await act(async () => { pending.resolve(recorder); });
    expect(await started).toBe(false);
    expect(recorder.stop).toHaveBeenCalledTimes(1);
    expect(voice.voiceRecording).toBe(false);
  });

  it("opens one recorder for a double tap on the mic", async () => {
    const pending = deferred<VoiceRecorder | null>();
    startMock.mockReturnValueOnce(pending.promise);
    await render(<Probe />);
    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    await act(async () => {
      first = voice.startRecording();
      second = voice.startRecording();
    });
    const recorder = fakeRecorder();
    await act(async () => { pending.resolve(recorder); });
    expect(await first).toBe(true);
    expect(await second).toBe(false);
    expect(startMock).toHaveBeenCalledTimes(1);
    expect(voice.voiceRecording).toBe(true);
  });

  it("stops the recording it owns on unmount, and deletes it", async () => {
    const recorder = fakeRecorder();
    startMock.mockResolvedValueOnce(recorder);
    const view = await render(<Probe />);
    await act(async () => { await voice.startRecording(); });
    expect(voice.voiceRecording).toBe(true);
    await view.unmount();
    expect(recorder.stop).toHaveBeenCalledTimes(1);
    await act(async () => {});
    expect(deleteVoiceRecording).toHaveBeenCalledWith("file:///rec.m4a");
  });

  it("deletes a recording the user cancelled (LEAK-04)", async () => {
    startMock.mockResolvedValueOnce(fakeRecorder());
    await render(<Probe />);
    await act(async () => { await voice.startRecording(); });
    await act(async () => { voice.cancelVoiceInput(); });
    expect(deleteVoiceRecording).toHaveBeenCalledWith("file:///rec.m4a");
    expect(transcribeSpeech).not.toHaveBeenCalled();
  });
});

describe("useVoiceInput permission and transcription errors (F8.2)", () => {
  const { reportRecoverableError } = jest.requireMock("@/lib/reportRecoverableError") as {
    reportRecoverableError: jest.Mock;
  };
  const { confirmDialog } = jest.requireMock("@/ui/overlay/dialogs") as { confirmDialog: jest.Mock };
  const { requestVoicePermission } = jest.requireMock("@/lib/speech/voiceAudio") as {
    requestVoicePermission: jest.Mock;
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });
  afterEach(() => {
    jest.clearAllMocks();
  });

  /** A recorder that heard speech, so finishing it sends the file to transcribe. */
  function speakingRecorder() {
    return {
      stop: jest.fn(async () => "file:///rec.m4a"),
      subscribeMetering: jest.fn((listener: (level: number) => void) => {
        listener(0.9);
        listener(0.9);
        return () => {};
      }),
    } satisfies VoiceRecorder;
  }

  async function transcribeFailingWith(error: Error) {
    startMock.mockResolvedValueOnce(speakingRecorder());
    (transcribeSpeech as jest.Mock).mockRejectedValueOnce(error);
    await render(<Probe />);
    await act(async () => { await voice.startRecording(); });
    await act(async () => { await voice.finishRecording(); });
  }

  it.each([
    ["transcribed", () => (transcribeSpeech as jest.Mock).mockResolvedValueOnce("hello")],
    ["refused", () => (transcribeSpeech as jest.Mock).mockRejectedValueOnce(new Error("server error"))],
  ])("deletes the recording once it was %s (LEAK-04)", async (_outcome, arrange) => {
    arrange();
    startMock.mockResolvedValueOnce(speakingRecorder());
    await render(<Probe />);
    await act(async () => { await voice.startRecording(); });
    await act(async () => { await voice.finishRecording(); });
    expect(transcribeSpeech).toHaveBeenCalledWith("tok", "file:///rec.m4a", expect.anything());
    expect(deleteVoiceRecording).toHaveBeenCalledWith("file:///rec.m4a");
  });

  it("offers Settings and opens no recorder when access is denied", async () => {
    requestVoicePermission.mockResolvedValueOnce({ granted: false, canAskAgain: false });
    await render(<Probe />);
    let started!: boolean;
    await act(async () => { started = await voice.startRecording(); });

    expect(started).toBe(false);
    expect(confirmDialog).toHaveBeenCalledWith({
      title: "chat.voice_permission_title",
      message: "chat.voice_permission_body",
      cancelLabel: "common.cancel",
      confirmLabel: "chat.location_open_settings",
    });
    expect(startMock).not.toHaveBeenCalled();
    expect(voice.voiceRecording).toBe(false);
  });

  it.each([
    [true, 1],
    [false, 0],
  ])("opens Settings only when the user taps it (tapped: %s)", async (tapped, opens) => {
    const openSettings = jest.spyOn(Linking, "openSettings").mockResolvedValue(undefined);
    confirmDialog.mockResolvedValueOnce(tapped);
    requestVoicePermission.mockResolvedValueOnce({ granted: false, canAskAgain: false });
    await render(<Probe />);
    await act(async () => { await voice.startRecording(); });
    expect(openSettings).toHaveBeenCalledTimes(opens);
    openSettings.mockRestore();
  });

  it("says the network failed when the upload could not reach the server", async () => {
    await transcribeFailingWith(new Error("Network request failed"));
    expect(reportRecoverableError).toHaveBeenCalledWith(null, "chat.voice_network_failed");
    expect(voice.voiceTranscribing).toBe(false);
  });

  it("says transcription failed for a server error", async () => {
    await transcribeFailingWith(Object.assign(new Error("Internal error"), { status: 500 }));
    expect(reportRecoverableError).toHaveBeenCalledWith(null, "chat.voice_transcribe_failed");
  });

  it("says it heard nothing when the server found no words", async () => {
    await transcribeFailingWith(new Error("transcribe_empty"));
    expect(reportRecoverableError).toHaveBeenCalledWith(null, "chat.voice_transcribe_empty");
  });
});

describe("useVoiceInput plan refusal", () => {
  it("opens the plans when the server says voice input is not in the plan", async () => {
    const { reportRecoverableError } = jest.requireMock("@/lib/reportRecoverableError") as {
      reportRecoverableError: jest.Mock;
    };
    const onPlanRequired = jest.fn();
    let planVoice!: ReturnType<typeof useVoiceInput>;
    function PlanProbe() {
      const value = useVoiceInput({
        token: "tok",
        onTranscript: jest.fn(),
        onPlanRequired,
        t: (key) => key,
      });
      React.useLayoutEffect(() => { planVoice = value; });
      return null;
    }
    const recorder = {
      stop: jest.fn(async () => "file:///rec.m4a"),
      subscribeMetering: jest.fn((listener: (level: number) => void) => {
        listener(0.9);
        listener(0.9);
        listener(0.9);
        return () => {};
      }),
    } satisfies VoiceRecorder;
    startMock.mockResolvedValueOnce(recorder);
    (transcribeSpeech as jest.Mock).mockRejectedValueOnce(
      Object.assign(new Error("Voice input isn't part of your plan."), { status: 403 }),
    );
    await render(<PlanProbe />);
    await act(async () => { await planVoice.startRecording(); });
    await act(async () => { await planVoice.finishRecording(); });
    expect(onPlanRequired).toHaveBeenCalledTimes(1);
    expect(reportRecoverableError).not.toHaveBeenCalled();
  });
});
