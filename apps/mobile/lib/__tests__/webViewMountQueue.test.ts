import {
  MAX_CONCURRENT_WEBVIEW_MOUNTS,
  isMountGranted,
  releaseMountTicket,
  requestMountTicket,
  resetWebViewMountQueue,
  subscribeMountQueue,
} from "@/lib/webViewMountQueue";

describe("webViewMountQueue", () => {
  afterEach(() => {
    resetWebViewMountQueue();
  });

  it("grants tickets immediately up to the concurrency cap", () => {
    const tickets = Array.from({ length: MAX_CONCURRENT_WEBVIEW_MOUNTS }, () =>
      requestMountTicket(),
    );

    tickets.forEach((ticket) => {
      expect(isMountGranted(ticket)).toBe(true);
    });
  });

  it("queues tickets beyond the cap until a slot frees up", () => {
    const granted = Array.from({ length: MAX_CONCURRENT_WEBVIEW_MOUNTS }, () =>
      requestMountTicket(),
    );
    const waiting = requestMountTicket();

    expect(isMountGranted(waiting)).toBe(false);

    releaseMountTicket(granted[0]);

    expect(isMountGranted(waiting)).toBe(true);
    // The freed slot went to the waiter, not re-granted to the released ticket.
    expect(isMountGranted(granted[0])).toBe(false);
  });

  it("removing a still-queued ticket does not grant an extra slot", () => {
    const granted = Array.from({ length: MAX_CONCURRENT_WEBVIEW_MOUNTS }, () =>
      requestMountTicket(),
    );
    const waitingA = requestMountTicket();
    const waitingB = requestMountTicket();

    releaseMountTicket(waitingA);

    expect(isMountGranted(waitingB)).toBe(false);
    expect(granted.every((ticket) => isMountGranted(ticket))).toBe(true);
  });

  it("promotes waiters in FIFO order as slots free up", () => {
    const granted = Array.from({ length: MAX_CONCURRENT_WEBVIEW_MOUNTS }, () =>
      requestMountTicket(),
    );
    const waitingA = requestMountTicket();
    const waitingB = requestMountTicket();

    releaseMountTicket(granted[0]);
    expect(isMountGranted(waitingA)).toBe(true);
    expect(isMountGranted(waitingB)).toBe(false);

    releaseMountTicket(granted[1]);
    expect(isMountGranted(waitingB)).toBe(true);
  });

  it("releasing a ticket twice is a no-op the second time", () => {
    const [first, second] = Array.from({ length: MAX_CONCURRENT_WEBVIEW_MOUNTS }, () =>
      requestMountTicket(),
    );
    const waiting = requestMountTicket();

    releaseMountTicket(first);
    expect(isMountGranted(waiting)).toBe(true);

    // Calling release again for the already-released ticket must not disturb
    // the waiter that already took its slot.
    releaseMountTicket(first);
    expect(isMountGranted(waiting)).toBe(true);
    expect(isMountGranted(second)).toBe(true);
  });

  it("notifies subscribers on every request and release", () => {
    const events: number[] = [];
    const unsubscribe = subscribeMountQueue(() => {
      events.push(events.length);
    });

    const a = requestMountTicket();
    releaseMountTicket(a);
    unsubscribe();

    expect(events.length).toBe(2);
  });

  it("stops notifying after unsubscribe", () => {
    const listener = jest.fn();
    const unsubscribe = subscribeMountQueue(listener);
    unsubscribe();

    requestMountTicket();

    expect(listener).not.toHaveBeenCalled();
  });

  it("an unknown ticket is simply not granted", () => {
    expect(isMountGranted(999_999)).toBe(false);
  });
});
