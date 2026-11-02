import { CONTEXT_REFRESH_STALE_MS, isContextFresh } from "@/lib/cache/contextRefresh";

describe("isContextFresh", () => {
  it("treats missing timestamps as stale", () => {
    expect(isContextFresh(undefined)).toBe(false);
  });

  it("is fresh inside the stale window and stale after", () => {
    const now = 1_000_000;
    expect(isContextFresh(now - CONTEXT_REFRESH_STALE_MS + 1, now)).toBe(true);
    expect(isContextFresh(now - CONTEXT_REFRESH_STALE_MS, now)).toBe(false);
  });

  it("is stale after the clock is set back, not fresh until it catches up", () => {
    const fetchedAt = 10_000_000;
    expect(isContextFresh(fetchedAt, fetchedAt - 60 * 60_000)).toBe(false);
  });
});
