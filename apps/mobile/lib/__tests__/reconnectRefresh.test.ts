import {
  connectionLostAt,
  onReconnect,
  readSinceLost,
  reconnectRefreshDelayMs,
  reportDisconnected,
  reportReconnected,
} from "@/lib/reconnectRefresh";

const appStateHandlers = new Set<(state: string) => void>();
jest.mock("react-native", () => ({
  AppState: {
    addEventListener: jest.fn((_event: string, handler: (state: string) => void) => {
      appStateHandlers.add(handler);
      return { remove: () => appStateHandlers.delete(handler) };
    }),
  },
}));

function appState(state: string): void {
  for (const handler of [...appStateHandlers]) handler(state);
}

/** A seeded generator (mulberry32): the same 10 000 draws on every run. */
function seeded(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4_294_967_296;
  };
}

/** How many of `delays` fall in each second of the 10 s spread. */
function perSecond(delays: number[]): number[] {
  const counts = new Array<number>(10).fill(0);
  for (const delay of delays) counts[Math.floor(delay / 1000)] += 1;
  return counts;
}

describe("reconnectRefreshDelayMs", () => {
  it("runs from 0 to just under 10 s", () => {
    expect(reconnectRefreshDelayMs(() => 0)).toBe(0);
    expect(reconnectRefreshDelayMs(() => 0.5)).toBe(5000);
    expect(reconnectRefreshDelayMs(() => 1 - Number.EPSILON)).toBe(9999);
  });

  it("spreads phones evenly over the 10 s, not in the same second", () => {
    // An even grid of draws lands an even count in every second.
    const grid = Array.from({ length: 1000 }, (_, i) => reconnectRefreshDelayMs(() => (i + 0.5) / 1000));
    expect(perSecond(grid)).toEqual(new Array(10).fill(100));

    // 10 000 phones: each second holds a tenth of them, within 10% (3 standard deviations).
    const random = seeded(2026);
    const phones = Array.from({ length: 10_000 }, () => reconnectRefreshDelayMs(random));
    for (const count of perSecond(phones)) expect(Math.abs(count - 1000)).toBeLessThan(100);
    const mean = phones.reduce((sum, delay) => sum + delay, 0) / phones.length;
    expect(Math.abs(mean - 5000)).toBeLessThan(100);
    expect(Math.min(...phones)).toBeLessThan(10);
    expect(Math.max(...phones)).toBeGreaterThan(9990);
  });

  it("stays within the 10 s with the platform's own random", () => {
    const delays = Array.from({ length: 10_000 }, () => reconnectRefreshDelayMs());
    expect(Math.min(...delays)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...delays)).toBeLessThan(10_000);
    expect(delays.every(Number.isInteger)).toBe(true);
  });
});

describe("onReconnect", () => {
  const refresh = jest.fn();
  let stop: () => void = () => {};

  beforeEach(() => {
    jest.useFakeTimers();
    refresh.mockClear();
  });
  afterEach(() => {
    stop();
    jest.useRealTimers();
  });

  it("reads once, when the wait ends", () => {
    stop = onReconnect(refresh, undefined, () => 3000);
    reportReconnected();
    jest.advanceTimersByTime(2999);
    expect(refresh).not.toHaveBeenCalled();
    jest.advanceTimersByTime(1);
    expect(refresh).toHaveBeenCalledTimes(1);
    jest.advanceTimersByTime(60_000);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("says when the connection was last lost", () => {
    jest.setSystemTime(5_000);
    reportDisconnected();
    jest.setSystemTime(9_000);
    reportReconnected();
    expect(connectionLostAt()).toBe(5_000);
    reportDisconnected();
    expect(connectionLostAt()).toBe(9_000);
  });

  it("counts a read that landed after the connection was lost, only", () => {
    jest.setSystemTime(5_000);
    reportDisconnected();
    expect(readSinceLost(undefined)).toBe(false);
    expect(readSinceLost(4_000)).toBe(false);
    expect(readSinceLost(5_000)).toBe(false);
    expect(readSinceLost(5_001)).toBe(true);
  });

  it("reads nothing before the API comes back", () => {
    stop = onReconnect(refresh, undefined, () => 0);
    reportDisconnected();
    jest.advanceTimersByTime(60_000);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("calls the wait off when the connection drops again", () => {
    stop = onReconnect(refresh, undefined, () => 5000);
    reportReconnected();
    jest.advanceTimersByTime(1000);
    reportDisconnected();
    jest.advanceTimersByTime(60_000);
    expect(refresh).not.toHaveBeenCalled();

    // Back again: a new wait, and its read.
    reportReconnected();
    jest.advanceTimersByTime(5000);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("calls the wait off when the app goes to the background, not for an iOS inactive blip", () => {
    stop = onReconnect(refresh, undefined, () => 5000);
    reportReconnected();
    appState("inactive");
    appState("active");
    jest.advanceTimersByTime(5000);
    expect(refresh).toHaveBeenCalledTimes(1);

    reportReconnected();
    appState("background");
    jest.advanceTimersByTime(60_000);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("calls the wait off when the screen loses focus", () => {
    stop = onReconnect(refresh, undefined, () => 5000);
    reportReconnected();
    stop();
    jest.advanceTimersByTime(60_000);
    reportReconnected();
    jest.advanceTimersByTime(60_000);
    expect(refresh).not.toHaveBeenCalled();
    expect(appStateHandlers.size).toBe(0);
  });

  it("reads only a list on screen when the API comes back and when the wait ends", () => {
    let onScreen = false;
    stop = onReconnect(refresh, () => onScreen, () => 5000);
    reportReconnected();
    onScreen = true;
    jest.advanceTimersByTime(5000);
    expect(refresh).not.toHaveBeenCalled();

    reportReconnected();
    onScreen = false;
    jest.advanceTimersByTime(5000);
    expect(refresh).not.toHaveBeenCalled();
    expect(appStateHandlers.size).toBe(0);
  });

  it("starts the wait over for a second return, and still reads once", () => {
    stop = onReconnect(refresh, undefined, () => 5000);
    reportReconnected();
    jest.advanceTimersByTime(4000);
    reportReconnected();
    jest.advanceTimersByTime(4000);
    expect(refresh).not.toHaveBeenCalled();
    jest.advanceTimersByTime(1000);
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
