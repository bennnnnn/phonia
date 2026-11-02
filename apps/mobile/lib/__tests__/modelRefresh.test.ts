import { shouldRefreshModels } from "@/lib/modelRefresh";

describe("shouldRefreshModels", () => {
  it("refreshes when never fetched before", () => {
    expect(shouldRefreshModels(0, 1_000_000, 5 * 60 * 1000)).toBe(true);
  });

  it("skips refresh when well within the TTL", () => {
    const now = 1_000_000;
    const lastFetchedAt = now - 60 * 1000; // 1 minute ago
    expect(shouldRefreshModels(lastFetchedAt, now, 5 * 60 * 1000)).toBe(false);
  });

  it("refreshes once the TTL has elapsed", () => {
    const now = 1_000_000;
    const lastFetchedAt = now - 6 * 60 * 1000; // 6 minutes ago
    expect(shouldRefreshModels(lastFetchedAt, now, 5 * 60 * 1000)).toBe(true);
  });

  it("refreshes exactly at the TTL boundary", () => {
    const now = 1_000_000;
    const ttl = 5 * 60 * 1000;
    const lastFetchedAt = now - ttl;
    expect(shouldRefreshModels(lastFetchedAt, now, ttl)).toBe(true);
  });

  it("refreshes after the clock is set back, not once it catches up", () => {
    const lastFetchedAt = 10_000_000;
    expect(shouldRefreshModels(lastFetchedAt, lastFetchedAt - 60 * 60 * 1000, 5 * 60 * 1000)).toBe(true);
  });
});
