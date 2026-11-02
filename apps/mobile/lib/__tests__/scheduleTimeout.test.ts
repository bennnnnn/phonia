import {
  clearScheduledTimeout,
  scheduleTimeout,
  type TimeoutHandle,
} from "@/lib/scheduleTimeout";

describe("scheduleTimeout", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("runs callback after delay and clears ref", () => {
    const ref: { current: TimeoutHandle } = { current: null };
    const fn = jest.fn();

    scheduleTimeout(ref, 150, fn);
    expect(ref.current).not.toBeNull();
    expect(fn).not.toHaveBeenCalled();

    jest.advanceTimersByTime(150);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(ref.current).toBeNull();
  });

  it("replaces a pending timeout", () => {
    const ref: { current: TimeoutHandle } = { current: null };
    const first = jest.fn();
    const second = jest.fn();

    scheduleTimeout(ref, 150, first);
    scheduleTimeout(ref, 150, second);

    jest.advanceTimersByTime(150);
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("clearScheduledTimeout cancels without running callback", () => {
    const ref: { current: TimeoutHandle } = { current: null };
    const fn = jest.fn();

    scheduleTimeout(ref, 150, fn);
    clearScheduledTimeout(ref);

    jest.advanceTimersByTime(150);
    expect(fn).not.toHaveBeenCalled();
    expect(ref.current).toBeNull();
  });
});
