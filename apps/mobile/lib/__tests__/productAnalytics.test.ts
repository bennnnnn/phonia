import { api } from "@/lib/api";
import { getSessionGeneration, getToken } from "@/lib/auth";
import {
  flushProductEvents,
  PRODUCT_EVENT_BATCH,
  PRODUCT_EVENT_FLUSH_MS,
  trackProductEvent,
} from "@/lib/productAnalytics";

jest.mock("@/lib/api", () => ({
  api: {
    recordProductEvents: jest.fn().mockResolvedValue(undefined),
  },
}));

jest.mock("@/lib/auth", () => ({
  getToken: jest.fn(async () => "token"),
  getSessionGeneration: jest.fn(() => 1),
}));

jest.mock("@/lib/installationId", () => ({
  getInstallationId: jest.fn().mockResolvedValue("installation-1"),
}));

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: {
    expoConfig: { version: "1.2.3" },
  },
}));

let mockOnAppState: ((state: string) => void) | undefined;
jest.mock("react-native", () => ({
  Platform: { OS: "ios" },
  AppState: {
    addEventListener: (_event: string, handler: (state: string) => void) => {
      mockOnAppState = handler;
      return { remove: () => undefined };
    },
  },
}));

const record = api.recordProductEvents as jest.Mock;
const sentEvents = () => record.mock.calls.flatMap(([, events]) => events);
const settle = () => jest.advanceTimersByTimeAsync(0);

const turnEvents = () => {
  trackProductEvent("chat_ttft", { latency_bucket: "lt500", transport: "ws", has_attachment: "no", sample_rate: "0.2" });
  trackProductEvent("chat_turn_outcome", { completion: "complete", error_code: "none", tool: "none", sample_rate: "0.2" });
};

describe("trackProductEvent", () => {
  beforeEach(async () => {
    jest.useFakeTimers();
    jest.mocked(getToken).mockResolvedValue("token");
    jest.mocked(getSessionGeneration).mockReturnValue(1);
    await flushProductEvents();
    record.mockClear();
    record.mockResolvedValue(undefined);
  });
  afterEach(() => {
    jest.useRealTimers();
  });

  it("sends two turns' chat events as one batch after 30 s", async () => {
    turnEvents();
    await jest.advanceTimersByTimeAsync(10_000);
    turnEvents();
    await jest.advanceTimersByTimeAsync(PRODUCT_EVENT_FLUSH_MS - 10_001);
    expect(record).not.toHaveBeenCalled();
    await jest.advanceTimersByTimeAsync(1);
    expect(record).toHaveBeenCalledTimes(1);
    expect(sentEvents().map((event) => event.name)).toEqual([
      "chat_ttft", "chat_turn_outcome", "chat_ttft", "chat_turn_outcome",
    ]);
  });

  it("sends only structured event metadata", async () => {
    trackProductEvent("paywall_viewed", { source: "settings" });
    await settle();
    expect(record).toHaveBeenCalledTimes(1);
    expect(record).toHaveBeenCalledWith("token", [
      {
        name: "paywall_viewed",
        properties: { source: "settings" },
        platform: "ios",
        app_version: "1.2.3",
        installation_id: "installation-1",
        client_at: expect.any(String),
      },
    ]);
  });

  it("sends a rarer event at once, with the chat events waiting", async () => {
    turnEvents();
    trackProductEvent("purchase_started", { plan: "pro" });
    await settle();
    expect(record).toHaveBeenCalledTimes(1);
    expect(sentEvents().map((event) => event.name)).toEqual([
      "chat_ttft", "chat_turn_outcome", "purchase_started",
    ]);
    // Nothing is left for the timer.
    await jest.advanceTimersByTimeAsync(PRODUCT_EVENT_FLUSH_MS);
    expect(record).toHaveBeenCalledTimes(1);
  });

  it("sends a full batch without waiting", async () => {
    for (let turn = 0; turn < PRODUCT_EVENT_BATCH / 2; turn += 1) turnEvents();
    await settle();
    expect(record).toHaveBeenCalledTimes(1);
    expect(record.mock.calls[0][1]).toHaveLength(PRODUCT_EVENT_BATCH);
  });

  it("sends what is waiting when the app goes to the background", async () => {
    turnEvents();
    mockOnAppState?.("inactive");
    await settle();
    expect(record).not.toHaveBeenCalled();
    mockOnAppState?.("background");
    await settle();
    expect(record).toHaveBeenCalledTimes(1);
  });

  it("drops events once signed out, and never sends one to a later account", async () => {
    jest.mocked(getToken).mockResolvedValueOnce(null);
    trackProductEvent("purchase_started", { plan: "pro" });
    await settle();
    expect(record).not.toHaveBeenCalled();

    turnEvents();
    jest.mocked(getSessionGeneration).mockReturnValue(2);
    trackProductEvent("purchase_started", { plan: "plus" });
    await settle();
    expect(sentEvents()).toEqual([expect.objectContaining({ name: "purchase_started", properties: { plan: "plus" } })]);
  });

  it("swallows delivery failures and does not resend", async () => {
    record.mockRejectedValueOnce(new Error("offline"));
    expect(() => trackProductEvent("purchase_started", { plan: "pro" })).not.toThrow();
    await settle();
    await jest.advanceTimersByTimeAsync(PRODUCT_EVENT_FLUSH_MS);
    expect(record).toHaveBeenCalledTimes(1);
  });
});
