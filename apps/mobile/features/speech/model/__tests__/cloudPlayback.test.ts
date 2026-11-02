import { playbackStatusFinished } from "@/features/speech/model/cloudPlayback";

describe("cloudPlayback", () => {
  it("finishes on didJustFinish or currentTime at duration", () => {
    expect(playbackStatusFinished({ didJustFinish: true })).toBe(true);
    expect(playbackStatusFinished({ currentTime: 0.74, duration: 0.75 })).toBe(true);
    expect(playbackStatusFinished({ currentTime: 0.1, duration: 0.75 })).toBe(false);
  });
});
