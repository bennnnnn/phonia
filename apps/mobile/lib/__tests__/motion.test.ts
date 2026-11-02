import { motionMs } from "@/lib/motionDuration";

describe("motionMs", () => {
  it("returns the duration when Reduce Motion is off", () => {
    expect(motionMs(280, false)).toBe(280);
  });

  it("collapses to zero when Reduce Motion is on", () => {
    expect(motionMs(280, true)).toBe(0);
  });
});
