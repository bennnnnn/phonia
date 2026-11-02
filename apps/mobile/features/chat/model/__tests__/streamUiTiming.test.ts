import { nextStreamUiFlushDelay, STREAM_UI_INTERVAL_MS } from "@/features/chat/model/streamUiTiming";

describe("nextStreamUiFlushDelay", () => {
  it("flushes immediately when enough time has elapsed", () => {
    expect(nextStreamUiFlushDelay(STREAM_UI_INTERVAL_MS)).toBe(0);
    expect(nextStreamUiFlushDelay(STREAM_UI_INTERVAL_MS + 10)).toBe(0);
  });

  it("returns the remaining wait when still inside the interval", () => {
    expect(nextStreamUiFlushDelay(0)).toBe(STREAM_UI_INTERVAL_MS);
    expect(nextStreamUiFlushDelay(20)).toBe(STREAM_UI_INTERVAL_MS - 20);
  });
});
