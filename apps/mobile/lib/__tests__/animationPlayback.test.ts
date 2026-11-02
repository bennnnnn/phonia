import {
  playbackStart,
  remainingPlaybackDuration,
} from "@/lib/animationPlayback";

describe("physics animation pause and resume", () => {
  it("continues from a paused frame", () => {
    expect(playbackStart(0.42)).toBe(0.42);
    expect(remainingPlaybackDuration(1600, 0.42)).toBe(928);
    expect(remainingPlaybackDuration(4000, 0.75)).toBe(1000);
  });

  it("replays from the beginning only after reaching the end", () => {
    expect(playbackStart(1)).toBe(0);
  });

  it("safely clamps invalid progress", () => {
    expect(playbackStart(-2)).toBe(0);
    expect(playbackStart(Number.NaN)).toBe(0);
    expect(remainingPlaybackDuration(1600, 4)).toBe(1);
  });
});
