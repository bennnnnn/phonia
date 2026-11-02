import { request } from "@/lib/api/client";

jest.mock("@/lib/config", () => ({ getApiUrl: () => "http://test.local" }));
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => 1,
  requireTokenSession: jest.fn(),
  SessionChangedError: class extends Error {},
  getRefreshToken: jest.fn(async () => null),
  setTokenPair: jest.fn(),
}));
const mockNoteApiFailure = jest.fn();
jest.mock("@/lib/sentry", () => ({
  noteApiFailure: (...args: unknown[]) => mockNoteApiFailure(...args),
}));

const mockFetch = jest.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => {
  mockFetch.mockReset();
  mockNoteApiFailure.mockReset();
});

function answer(status: number) {
  return { ok: status < 400, status, headers: { get: () => null }, text: async () => "{}" };
}

describe("a failed call's crumb", () => {
  it.each([404, 409, 422])("is not left for an expected %s refusal", async (status) => {
    mockFetch.mockResolvedValueOnce(answer(status));
    await expect(request("/chats/1", "")).rejects.toMatchObject({ status });
    expect(mockNoteApiFailure).not.toHaveBeenCalled();
  });

  it("is left for a server error, with the call's own id", async () => {
    mockFetch.mockResolvedValueOnce(answer(500));
    await expect(request("/search?q=secret", "")).rejects.toMatchObject({ status: 500 });
    const sent = (mockFetch.mock.calls[0][1] as { headers: Record<string, string> }).headers;
    expect(mockNoteApiFailure).toHaveBeenCalledWith("GET", "/search?q=secret", 500, sent["X-Request-ID"]);
  });

  it("is left when the API cannot be reached", async () => {
    mockFetch.mockRejectedValueOnce(new TypeError("Network request failed"));
    await expect(request("/chats", "")).rejects.toThrow();
    expect(mockNoteApiFailure).toHaveBeenCalledWith("GET", "/chats", null, expect.any(String));
  });
});
