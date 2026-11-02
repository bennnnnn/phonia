import { parseChatWsPayload } from "@/features/chat/model/socketReduce";
import { CHAT_EVENT_SAMPLE_RATE } from "@/features/chat/model/chatEventSample";
import { reportChatTtft } from "@/features/chat/model/latencyReporter";
import {
  chatPaintBucket,
  chatTtftBucket,
  clearPendingChatTtft,
  markChatBubblePainted,
  markChatFirstToken,
  markChatTtftStart,
  markChatTtftTransport,
} from "@/features/chat/model/latency";

jest.mock("@/features/chat/model/latencyReporter", () => ({
  reportChatTtft: jest.fn(async () => undefined),
}));

/** The tap on Send. */
const startedAt = Date.parse("2026-01-01T00:00:00.000Z");
const devHolder = globalThis as unknown as { __DEV__?: boolean };
const originalDev = devHolder.__DEV__;

async function flushTtftReport(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

describe("chatTtftBucket", () => {
  it.each([
    [0, "lt500"],
    [499, "lt500"],
    [500, "500_999"],
    [999, "500_999"],
    [1_000, "1000_1999"],
    [1_999, "1000_1999"],
    [2_000, "2000_3999"],
    [3_999, "2000_3999"],
    [4_000, "4000_5999"],
    [5_999, "4000_5999"],
    [6_000, "6000_plus"],
  ])("buckets %sms as %s", (elapsedMs, expected) => {
    expect(chatTtftBucket(elapsedMs as number)).toBe(expected);
  });
});

describe("chatPaintBucket", () => {
  it.each([
    [0, "lt50"],
    [49, "lt50"],
    [50, "50_99"],
    [100, "100_249"],
    [250, "250_499"],
    [500, "500_999"],
    [999, "500_999"],
    [1_000, "1000_plus"],
    [Number.NaN, "lt50"],
  ])("buckets %sms as %s", (elapsedMs, expected) => {
    expect(chatPaintBucket(elapsedMs as number)).toBe(expected);
  });
});

describe("pending chat TTFT samples", () => {
  beforeEach(() => {
    devHolder.__DEV__ = false;
    clearPendingChatTtft();
    jest.mocked(reportChatTtft).mockClear();
    jest.spyOn(Date, "now").mockReturnValue(startedAt + 750);
    // Every turn in the sample unless a case says otherwise.
    jest.spyOn(Math, "random").mockReturnValue(0);
  });

  afterEach(() => {
    clearPendingChatTtft();
    jest.restoreAllMocks();
    if (originalDev === undefined) {
      delete devHolder.__DEV__;
    } else {
      devHolder.__DEV__ = originalDev;
    }
  });

  it("reports the originating turn after its token is accepted", async () => {
    markChatTtftStart("turn-b", startedAt, true);
    markChatTtftTransport("turn-b", "sse");
    markChatFirstToken("turn-b", "token");
    await flushTtftReport();
    expect(reportChatTtft).toHaveBeenCalledTimes(1);
    expect(reportChatTtft).toHaveBeenCalledWith({
      latencyBucket: "500_999",
      transport: "sse",
      hasAttachment: true,
    });
  });

  it("does not let leftover chat A consume chat B's sample", async () => {
    markChatTtftStart("turn-a", startedAt, false);
    markChatTtftStart("turn-b", startedAt, true);
    markChatTtftTransport("turn-a", "sse");
    parseChatWsPayload(JSON.stringify({ type: "token", content: "hi" }));
    markChatFirstToken("turn-a", "token");
    await flushTtftReport();
    expect(reportChatTtft).not.toHaveBeenCalled();

    markChatFirstToken("turn-b", "token");
    await flushTtftReport();
    expect(reportChatTtft).toHaveBeenCalledTimes(1);
    expect(reportChatTtft).toHaveBeenCalledWith({
      latencyBucket: "500_999",
      transport: "ws",
      hasAttachment: true,
    });
  });

  it("does not let a later regenerate consume a cancelled send's sample", async () => {
    markChatTtftStart("turn-a", startedAt, false);
    clearPendingChatTtft("turn-a");
    markChatFirstToken("turn-a", "token");
    markChatFirstToken(undefined, "token");
    await flushTtftReport();
    expect(reportChatTtft).not.toHaveBeenCalled();
  });

  it("reports one turn in five, and a turn left out drops the one before it", async () => {
    markChatTtftStart("turn-a", startedAt, false);
    jest.spyOn(Math, "random").mockReturnValue(CHAT_EVENT_SAMPLE_RATE);
    markChatTtftStart("turn-b", startedAt, false);
    markChatFirstToken("turn-a", "token");
    markChatFirstToken("turn-b", "token");
    await flushTtftReport();
    expect(reportChatTtft).not.toHaveBeenCalled();
  });

  it("never samples a development build", async () => {
    devHolder.__DEV__ = true;
    markChatTtftStart("turn-a", startedAt, false);
    markChatFirstToken("turn-a", "token");
    await flushTtftReport();
    expect(reportChatTtft).not.toHaveBeenCalled();
  });

  it("does not clear a newer send when discarding an older turn", async () => {
    markChatTtftStart("turn-a", startedAt, false);
    markChatTtftStart("turn-b", startedAt, true);
    clearPendingChatTtft("turn-a");
    markChatFirstToken("turn-b", "token");
    await flushTtftReport();
    expect(reportChatTtft).toHaveBeenCalledTimes(1);
  });

  it("reports tap -> bubble painted with the sample, from the first paint only", async () => {
    const now = jest.spyOn(Date, "now");
    markChatTtftStart("turn-a", startedAt, false);
    now.mockReturnValue(startedAt + 20);
    markChatBubblePainted("turn-a");
    now.mockReturnValue(startedAt + 400);
    markChatBubblePainted("turn-a");
    markChatBubblePainted("turn-b");
    now.mockReturnValue(startedAt + 1_200);
    markChatFirstToken("turn-a", "token");
    await flushTtftReport();
    expect(reportChatTtft).toHaveBeenCalledWith({
      latencyBucket: "1000_1999",
      transport: "ws",
      hasAttachment: false,
      paintBucket: "lt50",
    });
  });

  it("leaves the paint out when no frame ran before the first token", async () => {
    markChatTtftStart("turn-a", startedAt, false);
    markChatFirstToken("turn-a", "token");
    await flushTtftReport();
    expect(jest.mocked(reportChatTtft).mock.calls[0][0]).not.toHaveProperty("paintBucket");
  });
});
