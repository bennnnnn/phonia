import { hasPlanFeature, planNameKey, planOf, upgradeTargets } from "@/lib/plan";

describe("plan helpers", () => {
  it("treats anything unknown as free, never as paid", () => {
    expect(planOf(null)).toBe("free");
    expect(planOf({ plan: "enterprise" })).toBe("free");
    expect(planOf({ plan: "plus" })).toBe("plus");
  });

  it("reads features from the server when it lists them", () => {
    const user = { plan: "plus", features: ["speech_tts"] };
    expect(hasPlanFeature(user, "speech_tts")).toBe(true);
    expect(hasPlanFeature(user, "live_talk")).toBe(false);
    expect(hasPlanFeature(user, "all_models")).toBe(false);
  });

  it("falls back to each plan's defaults for an older cached user", () => {
    expect(hasPlanFeature({ plan: "free" }, "speech_transcription")).toBe(false);
    expect(hasPlanFeature({ plan: "free" }, "image_generation")).toBe(true);
    expect(hasPlanFeature({ plan: "plus" }, "speech_transcription")).toBe(true);
    expect(hasPlanFeature({ plan: "plus" }, "live_talk")).toBe(false);
    expect(hasPlanFeature({ plan: "pro" }, "live_talk")).toBe(true);
  });

  it("offers the next plans up and nothing past the top", () => {
    expect(upgradeTargets("free")).toEqual(["plus", "pro"]);
    expect(upgradeTargets("plus")).toEqual(["pro"]);
    expect(upgradeTargets("pro")).toEqual([]);
  });

  it("keeps display names in i18n", () => {
    expect(planNameKey("plus")).toBe("plans.plus");
  });
});
