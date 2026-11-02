import { EAGER_CONNECT_DEBOUNCE_MS, WS_CONNECT_TIMEOUT_MS } from "@/features/chat/model/wsConnect";

describe("chatWsConnect", () => {
  it("leaves a high-latency handshake time to finish, but fails over within a few seconds", () => {
    expect(WS_CONNECT_TIMEOUT_MS).toBe(2_500);
    expect(WS_CONNECT_TIMEOUT_MS).toBeLessThanOrEqual(3_000);
    expect(EAGER_CONNECT_DEBOUNCE_MS).toBe(100);
  });
});
