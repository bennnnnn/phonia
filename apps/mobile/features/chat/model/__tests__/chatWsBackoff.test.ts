import { createWsBackoff, WS_RETRY_BASE_MS, WS_RETRY_MAX_MS } from "@/features/chat/model/wsBackoff";

describe("createWsBackoff", () => {
  let now = 0;
  const clock = () => now;

  beforeEach(() => {
    now = 1_000_000;
  });

  it("keeps sends off the socket only until the wait ends", () => {
    const backoff = createWsBackoff(clock);
    expect(backoff.cooling()).toBe(false);
    backoff.fail();
    expect(backoff.cooling()).toBe(true);
    now += WS_RETRY_BASE_MS - 1;
    expect(backoff.cooling()).toBe(true);
    now += 1;
    expect(backoff.cooling()).toBe(false);
  });

  it("doubles the wait for each failure in a row, up to the cap", () => {
    const backoff = createWsBackoff(clock);
    const waits: number[] = [];
    for (let failure = 0; failure < 8; failure += 1) {
      const failedAt = now;
      backoff.fail();
      while (backoff.cooling()) now += 1_000;
      waits.push(now - failedAt);
    }
    expect(waits.slice(0, 3)).toEqual([WS_RETRY_BASE_MS, 2 * WS_RETRY_BASE_MS, 4 * WS_RETRY_BASE_MS]);
    expect(waits.at(-1)).toBe(WS_RETRY_MAX_MS);
  });

  it("starts over after a turn the socket completed", () => {
    const backoff = createWsBackoff(clock);
    backoff.fail();
    backoff.fail();
    backoff.succeed();
    expect(backoff.cooling()).toBe(false);
    backoff.fail();
    now += WS_RETRY_BASE_MS;
    expect(backoff.cooling()).toBe(false);
  });
});
