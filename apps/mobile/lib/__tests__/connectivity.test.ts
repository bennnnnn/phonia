jest.mock("@/lib/config", () => ({
  getApiUrl: () => "http://test.local",
}));

jest.mock("@/lib/auth", () => ({
  getRefreshToken: jest.fn(),
  setTokenPair: jest.fn(),
}));

import { chatWebSocketUrl, checkHealth } from "@/lib/api/connectivity";

const mockFetch = jest.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => {
  mockFetch.mockReset();
});

describe("api connectivity", () => {
  it("chatWebSocketUrl converts http base to ws", () => {
    expect(chatWebSocketUrl("abc-123")).toBe("ws://test.local/ws/chats/abc-123");
  });

  it("checkHealth returns true when the API and its dependencies answer", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true });
    await expect(checkHealth()).resolves.toBe(true);
    // Not liveness (/health answers 200 with the database down), and an AbortSignal.
    expect(mockFetch).toHaveBeenCalledWith(
      "http://test.local/health/dependencies",
      expect.objectContaining({
        signal: expect.any(AbortSignal),
        headers: { "X-Request-ID": expect.stringMatching(/^[A-Za-z0-9_-]{1,64}$/) },
      }),
    );
  });

  it("checkHealth returns false on network error", async () => {
    mockFetch.mockRejectedValueOnce(new Error("offline"));
    await expect(checkHealth()).resolves.toBe(false);
  });

  it("checkHealth returns false when response is not ok", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 503 });
    await expect(checkHealth()).resolves.toBe(false);
  });

  it("checkHealth returns true from an API that predates the dependency check (404)", async () => {
    // A rollback, or an app update out before the API's: the server is up, as /health said.
    mockFetch.mockResolvedValueOnce({ ok: false, status: 404 });
    await expect(checkHealth()).resolves.toBe(true);
  });
});
