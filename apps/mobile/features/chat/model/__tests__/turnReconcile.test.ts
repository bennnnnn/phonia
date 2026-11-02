import type { Message } from "@/lib/api";
import { ApiRequestError } from "@/lib/api/errorBody";
import { MESSAGE_PAGE_SIZE } from "@/features/chat/model/constants";
import {
  DROPPED_TURN_MAX_WAIT_MS,
  DROPPED_TURN_POLL_MS,
  DROPPED_TURN_POLLS,
  DROPPED_TURN_PROBE_ROWS,
  DUPLICATE_TURN_POLLS,
  droppedTurnState,
  droppedTurnWaitMs,
  duplicateTurnPollMs,
  knownServerIds,
  mergeReconciledPage,
  pollDroppedTurn,
} from "@/features/chat/model/turnReconcile";

const id = (n: number) => `0190a000-0000-7000-8000-${String(n).padStart(12, "0")}`;
const msg = (messageId: string, role: Message["role"], content = messageId): Message => ({
  id: messageId,
  role,
  content,
  model: null,
  created_at: "t",
});

const before = [msg(id(1), "user"), msg(id(2), "assistant")];
const known = knownServerIds([...before, msg("local-9", "user"), msg("streaming", "assistant")]);

describe("knownServerIds", () => {
  it("keeps only server rows, never the turn's local bubbles", () => {
    expect([...known]).toEqual([id(1), id(2)]);
  });
});

describe("droppedTurnState", () => {
  it.each([
    ["missing", before],
    ["saved", [...before, msg(id(3), "user")]],
    ["answered", [...before, msg(id(3), "user"), msg(id(4), "assistant")]],
  ] as const)("%s", (state, page) => {
    expect(droppedTurnState([...page], known)).toBe(state);
  });

  it("an older reply is not this turn's answer", () => {
    expect(droppedTurnState([msg(id(3), "user"), ...before.slice(1)], known)).toBe("saved");
  });
});

describe("mergeReconciledPage", () => {
  it("swaps the local bubbles for the saved turn and keeps older loaded pages", () => {
    const older = msg(id(0), "assistant", "older page");
    const previous = [older, ...before, msg("local-9", "user", "q"), msg("streaming", "assistant", "")];
    const page = [...before, msg(id(3), "user", "q"), msg(id(4), "assistant", "a")];
    expect(mergeReconciledPage(previous, page).map((m) => m.id)).toEqual([
      id(0), id(1), id(2), id(3), id(4),
    ]);
  });

  it("a first turn has no older rows to keep", () => {
    const page = [msg(id(3), "user"), msg(id(4), "assistant")];
    expect(mergeReconciledPage([msg("local-1", "user"), msg("streaming", "assistant")], page)).toEqual(page);
  });

  it("keeps a message sent while the turn saved, below the saved reply", () => {
    const queued = msg("local-10", "user", "next");
    const previous = [...before, msg("local-9", "user", "q"), msg("streaming", "assistant", "a"), queued];
    const page = [...before, msg(id(3), "user", "q"), msg(id(4), "assistant", "a")];
    expect(mergeReconciledPage(previous, page)).toEqual([...page, queued]);
  });
});

describe("pollDroppedTurn", () => {
  const wait = jest.fn(async (_ms: number) => {});
  beforeEach(() => wait.mockClear());

  it("polls a few rows and reads the full page once, when the reply has landed", async () => {
    const answered = [...before, msg(id(3), "user"), msg(id(4), "assistant")];
    const fullPage = [msg(id(0), "assistant"), ...answered];
    const fetchPage = jest.fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce([...before, msg(id(3), "user")])
      .mockResolvedValueOnce(answered)
      .mockResolvedValueOnce(fullPage);
    const result = await pollDroppedTurn({ fetchPage, known, stillWaiting: () => true, wait });
    expect(result).toEqual({ state: "answered", page: fullPage });
    expect(fetchPage.mock.calls.map(([limit]) => limit)).toEqual([
      DROPPED_TURN_PROBE_ROWS, DROPPED_TURN_PROBE_ROWS, DROPPED_TURN_PROBE_ROWS, MESSAGE_PAGE_SIZE,
    ]);
  });

  it("reports the last state when the polls run out, with no page to settle", async () => {
    const fetchPage = jest.fn().mockResolvedValue(before);
    const result = await pollDroppedTurn({ fetchPage, known, stillWaiting: () => true, wait });
    expect(result).toEqual({ state: "missing", page: null });
    expect(fetchPage).toHaveBeenCalledTimes(DROPPED_TURN_POLLS);
    expect(fetchPage).not.toHaveBeenCalledWith(MESSAGE_PAGE_SIZE);
  });

  it("polls again when the full page fails after the reply landed", async () => {
    const answered = [...before, msg(id(3), "user"), msg(id(4), "assistant")];
    const fetchPage = jest.fn()
      .mockResolvedValueOnce(answered)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(answered)
      .mockResolvedValueOnce(answered);
    const result = await pollDroppedTurn({ fetchPage, known, stillWaiting: () => true, wait });
    expect(result).toEqual({ state: "answered", page: answered });
    expect(fetchPage).toHaveBeenCalledTimes(4);
  });

  it("spreads each wait by a quarter either way", async () => {
    expect(droppedTurnWaitMs(() => 0)).toBe(DROPPED_TURN_POLL_MS * 0.75);
    expect(droppedTurnWaitMs(() => 0.5)).toBe(DROPPED_TURN_POLL_MS);
    expect(droppedTurnWaitMs(() => 1)).toBe(DROPPED_TURN_MAX_WAIT_MS);
    const fetchPage = jest.fn().mockResolvedValue(before);
    const draws = [0, 1, 0.5];
    await pollDroppedTurn({
      fetchPage, known, stillWaiting: () => true, polls: 3, wait, random: () => draws.shift() ?? 0,
    });
    expect(wait.mock.calls.map(([ms]) => ms)).toEqual([1_500, 2_500, 2_000]);
  });

  it("waits as long as a refused poll's Retry-After asks, spread up to a quarter past it", async () => {
    const fetchPage = jest.fn()
      .mockRejectedValueOnce(new ApiRequestError(503, "", 5_000))
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(before);
    await pollDroppedTurn({ fetchPage, known, stillWaiting: () => true, polls: 3, wait, random: () => 1 });
    expect(wait.mock.calls.map(([ms]) => ms)).toEqual([DROPPED_TURN_MAX_WAIT_MS, 6_250, DROPPED_TURN_MAX_WAIT_MS]);
  });

  it("polls a server answering 503 Retry-After: 5 for 30 s five times, not fourteen", async () => {
    let clock = 0;
    const polledAt: number[] = [];
    const fetchPage = jest.fn(async () => {
      polledAt.push(clock);
      if (clock < 30_000) throw new ApiRequestError(503, "{\"detail\":\"Service temporarily unavailable.\"}", 5_000);
      return before;
    });
    await pollDroppedTurn({
      fetchPage, known, stillWaiting: () => true, random: () => 0.5,
      wait: async (ms) => { clock += ms; },
    });
    expect(polledAt.filter((at) => at < 30_000)).toHaveLength(5);
  });

  it("is unknown when no reload worked, and honours a shorter poll count", async () => {
    const fetchPage = jest.fn().mockRejectedValue(new Error("offline"));
    const result = await pollDroppedTurn({ fetchPage, known, stillWaiting: () => true, polls: 3, wait });
    expect(result).toEqual({ state: "unknown", page: null });
    expect(fetchPage).toHaveBeenCalledTimes(3);
  });

  it("returns null once the wait is abandoned", async () => {
    let waiting = true;
    const fetchPage = jest.fn(async () => {
      waiting = false; // Stop, a new send, or another chat while this reload ran
      return [...before, msg(id(3), "user"), msg(id(4), "assistant")];
    });
    expect(await pollDroppedTurn({ fetchPage, known, stillWaiting: () => waiting, wait })).toBeNull();
    expect(await pollDroppedTurn({ fetchPage, known, stillWaiting: () => false, wait })).toBeNull();
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it("returns null when the wait is abandoned while the full page loads", async () => {
    let waiting = true;
    const answered = [...before, msg(id(3), "user"), msg(id(4), "assistant")];
    const fetchPage = jest.fn(async (limit: number) => {
      if (limit === MESSAGE_PAGE_SIZE) waiting = false;
      return answered;
    });
    expect(await pollDroppedTurn({ fetchPage, known, stillWaiting: () => waiting, wait })).toBeNull();
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });
});

describe("following a turn the server reported as a duplicate", () => {
  it("waits longer between polls as it goes, for about five minutes", () => {
    const waits = Array.from({ length: DUPLICATE_TURN_POLLS }, (_, poll) => duplicateTurnPollMs(poll));
    expect(waits[0]).toBe(DROPPED_TURN_POLL_MS);
    expect(waits[1]).toBeGreaterThan(waits[0]);
    expect(Math.max(...waits)).toBe(15_000);
    const total = waits.reduce((sum, ms) => sum + ms, 0);
    expect(total).toBeGreaterThan(4 * 60_000);
    expect(total).toBeLessThan(6 * 60_000);
  });

  it("polls on the schedule it is given", async () => {
    const wait = jest.fn(async (_ms: number) => {});
    const fetchPage = jest.fn().mockResolvedValue(before);
    await pollDroppedTurn({
      // The middle of the jitter: each wait is exactly its schedule's.
      fetchPage, known, stillWaiting: () => true, polls: 4, pollMs: duplicateTurnPollMs, wait, random: () => 0.5,
    });
    expect(wait.mock.calls.map(([ms]) => ms)).toEqual([0, 1, 2, 3].map(duplicateTurnPollMs));
  });
});
