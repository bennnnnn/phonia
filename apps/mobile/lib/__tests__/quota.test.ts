import {
  formatUsageSummary,
  usageRemainingPercent,
  usageUsedPercent,
  usageUsedTokens,
} from "@/lib/quota";

describe("quota helpers", () => {
  const usage = {
    date: "2026-06-27",
    input_tokens: 1000,
    output_tokens: 2000,
    daily_limit: 100_000,
    used_tokens: 12_000,
    remaining: 88_000,
  };

  it("usageUsedTokens prefers authoritative used_tokens", () => {
    expect(usageUsedTokens(usage)).toBe(12_000);
    expect(
      usageUsedTokens({ ...usage, used_tokens: undefined, remaining: 5_000 }),
    ).toBe(95_000);
  });

  it("usageUsedPercent and usageRemainingPercent stay in sync", () => {
    expect(usageUsedPercent(usage)).toBe(12);
    expect(usageRemainingPercent(usage)).toBe(88);
  });

  it("formatUsageSummary is plan-aware", () => {
    const t = (key: string, opts?: Record<string, unknown>) =>
      key === "settings.usage_left"
        ? `${opts?.pct}% free left`
        : key === "settings.usage_left_paid"
          ? `${opts?.pct}% pro left`
          : key;

    expect(formatUsageSummary(usage, false, t)).toBe("88% free left");
    expect(formatUsageSummary(usage, true, t)).toBe("88% pro left");
  });
});
