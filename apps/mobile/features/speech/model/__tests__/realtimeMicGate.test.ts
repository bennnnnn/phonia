import { createRealtimeMicGate } from "@/features/speech/model/realtimeMicGate";

describe("createRealtimeMicGate", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("restarting a timer replaces the pending one, and only its event arrives", () => {
    const elapsed = jest.fn();
    const gate = createRealtimeMicGate([], elapsed);
    gate.start("mic_resume", 12_000, { type: "playback_fallback" });
    gate.start("mic_resume", 500, { type: "resume_mic" });
    gate.start("session_ready", 1_500, { type: "session_ready", reason: "warmup" });
    jest.advanceTimersByTime(12_000);
    expect(elapsed.mock.calls).toEqual([[{ type: "resume_mic" }], [{ type: "session_ready", reason: "warmup" }]]);
  });

  it("clearAll stops both timers", () => {
    const elapsed = jest.fn();
    const gate = createRealtimeMicGate([], elapsed);
    gate.start("mic_resume", 500, { type: "resume_mic" });
    gate.start("session_ready", 2_500, { type: "session_ready", reason: "fallback" });
    gate.clearAll();
    expect(jest.getTimerCount()).toBe(0);
  });

  it("sets every mic track even when one refuses", () => {
    const stubborn = {
      get enabled() {
        return true;
      },
      set enabled(_value: boolean) {
        throw new Error("ended");
      },
    };
    const track = { enabled: true };
    createRealtimeMicGate([stubborn, track], jest.fn()).setMic(false);
    expect(track.enabled).toBe(false);
  });
});
