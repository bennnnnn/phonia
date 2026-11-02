import {
  accessTokenNeedsRefresh,
  request,
  setTokenRefreshHandler,
  setUnauthorizedHandler,
} from "@/lib/api/client";

jest.mock("@/lib/config", () => ({
  getApiUrl: () => "http://test.local",
}));

const mockGetRefreshToken = jest.fn();
const mockSetTokenPair = jest.fn();
const mockRequireTokenSession = jest.fn();
let mockSessionGeneration = 0;
/** Each test is a sign-in of its own: a refresh one test made is not another's (`lastRefreshed`). */
let signIns = 0;

jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => mockSessionGeneration,
  requireTokenSession: (...args: unknown[]) => mockRequireTokenSession(...args),
  SessionChangedError: class extends Error {
    constructor() {
      super("Session changed");
      this.name = "SessionChangedError";
    }
  },
  getRefreshToken: (...args: unknown[]) => mockGetRefreshToken(...args),
  setTokenPair: (...args: unknown[]) => mockSetTokenPair(...args),
}));

const mockFetch = jest.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

function accessToken(expSeconds: number): string {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value))
      .replace(/=/g, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode({ sub: "u1", exp: expSeconds })}.signature`;
}

beforeEach(() => {
  jest.clearAllMocks();
  mockSessionGeneration = (signIns += 100);
  mockGetRefreshToken.mockResolvedValue("refresh-token");
  mockSetTokenPair.mockResolvedValue(true);
  setUnauthorizedHandler(null);
  setTokenRefreshHandler(null);
});

it("recognizes expired and near-expiry access tokens without rejecting opaque tokens", () => {
  const nowMs = 2_000_000;
  expect(accessTokenNeedsRefresh(accessToken(1_900), nowMs)).toBe(true);
  expect(accessTokenNeedsRefresh(accessToken(2_020), nowMs)).toBe(true);
  expect(accessTokenNeedsRefresh(accessToken(2_120), nowMs)).toBe(false);
  expect(accessTokenNeedsRefresh("opaque-token", nowMs)).toBe(false);
});

it("refreshes an expired token before sending the authenticated request", async () => {
  const expired = accessToken(Math.floor(Date.now() / 1000) - 60);
  mockFetch
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: "fresh-access",
        refresh_token: "fresh-refresh",
      }),
    })
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ greeting: "hi" }),
    });

  await expect(request<{ greeting: string }>("/home", expired)).resolves.toEqual({
    greeting: "hi",
  });

  expect(mockFetch).toHaveBeenCalledTimes(2);
  expect(mockFetch.mock.calls[0][0]).toBe("http://test.local/auth/refresh");
  expect(mockFetch.mock.calls[1][0]).toBe("http://test.local/home");
  expect(mockFetch.mock.calls[1][1]?.headers).toMatchObject({
    Authorization: "Bearer fresh-access",
  });
  expect(mockSetTokenPair).toHaveBeenCalledWith("fresh-access", "fresh-refresh", mockSessionGeneration);
});
