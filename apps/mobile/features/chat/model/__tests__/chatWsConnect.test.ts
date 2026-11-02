import { EAGER_CONNECT_DEBOUNCE_MS, WS_CONNECT_TIMEOUT_MS } from "@/features/chat/model/wsConnect";

describe("chatWsConnect", () => {
  it("fails over quickly when WebSocket handshakes stall", () => {
    expect(WS_CONNECT_TIMEOUT_MS).toBe(900);
    expect(WS_CONNECT_TIMEOUT_MS).toBeLessThan(1_000);
    expect(EAGER_CONNECT_DEBOUNCE_MS).toBe(100);
  });
});
