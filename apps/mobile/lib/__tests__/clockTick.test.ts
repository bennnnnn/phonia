import { subscribeClockTick } from "@/lib/clockTick";

describe("clockTick", () => {
  let unsubscribers: Array<() => void>;

  beforeEach(() => {
    jest.useFakeTimers();
    unsubscribers = [];
  });

  afterEach(() => {
    // Idempotent: unsubscribe() tolerates being called more than once, so
    // any manual unsubscribes earlier in a test are harmless to repeat here.
    unsubscribers.forEach((unsubscribe) => unsubscribe());
    jest.useRealTimers();
  });

  function subscribe(listener: () => void): () => void {
    const unsubscribe = subscribeClockTick(listener);
    unsubscribers.push(unsubscribe);
    return unsubscribe;
  }

  it("shares a single underlying timer across multiple subscribers", () => {
    subscribe(jest.fn());
    expect(jest.getTimerCount()).toBe(1);

    subscribe(jest.fn());
    subscribe(jest.fn());
    expect(jest.getTimerCount()).toBe(1);
  });

  it("broadcasts every tick to every subscriber", () => {
    const a = jest.fn();
    const b = jest.fn();
    subscribe(a);
    subscribe(b);

    jest.advanceTimersByTime(3000);

    expect(a).toHaveBeenCalledTimes(3);
    expect(b).toHaveBeenCalledTimes(3);
  });

  it("stops notifying a listener once it unsubscribes, without affecting the others", () => {
    const a = jest.fn();
    const b = jest.fn();
    const unsubscribeA = subscribe(a);
    subscribe(b);

    jest.advanceTimersByTime(1000);
    unsubscribeA();
    jest.advanceTimersByTime(2000);

    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(3);
  });

  it("clears the underlying timer once the last subscriber unsubscribes", () => {
    const unsubscribe = subscribe(jest.fn());
    expect(jest.getTimerCount()).toBe(1);

    unsubscribe();
    expect(jest.getTimerCount()).toBe(0);
  });

  it("starts a fresh timer for a new subscriber after the shared timer has stopped", () => {
    const unsubscribeFirst = subscribe(jest.fn());
    unsubscribeFirst();
    expect(jest.getTimerCount()).toBe(0);

    const listener = jest.fn();
    subscribe(listener);
    expect(jest.getTimerCount()).toBe(1);

    jest.advanceTimersByTime(1000);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("returns an idempotent unsubscribe and allows resubscribing afterward", () => {
    const listener = jest.fn();
    const unsubscribe = subscribe(listener);

    unsubscribe();
    expect(() => unsubscribe()).not.toThrow();
    expect(jest.getTimerCount()).toBe(0);

    const listener2 = jest.fn();
    subscribe(listener2);

    jest.advanceTimersByTime(1000);
    expect(listener2).toHaveBeenCalledTimes(1);
  });
});
