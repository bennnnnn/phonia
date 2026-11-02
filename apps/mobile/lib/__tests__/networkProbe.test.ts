const mockRefresh = jest.fn();
const mockCheckHealth = jest.fn();

jest.mock("@react-native-community/netinfo", () => ({
  __esModule: true,
  default: {
    refresh: (...args: unknown[]) => mockRefresh(...args),
  },
}));

jest.mock("@/lib/api/connectivity", () => ({
  checkHealth: (...args: unknown[]) => mockCheckHealth(...args),
}));

import {
  checkPublicReachability,
  classifyConnectivity,
  resolveConnectivity,
} from "@/lib/networkProbe";

const mockFetch = jest.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => {
  mockRefresh.mockReset();
  mockCheckHealth.mockReset();
  mockFetch.mockReset();
});

describe("classifyConnectivity", () => {
  it("is online when the API is reachable", () => {
    expect(classifyConnectivity(true, false)).toBe("online");
    expect(classifyConnectivity(true, true)).toBe("online");
  });

  it("is api_unreachable when the internet works but the API does not", () => {
    expect(classifyConnectivity(false, true)).toBe("api_unreachable");
  });

  it("is no_internet when both probes fail", () => {
    expect(classifyConnectivity(false, false)).toBe("no_internet");
  });
});

describe("checkPublicReachability", () => {
  it("returns true on generate_204", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });
    await expect(checkPublicReachability()).resolves.toBe(true);
  });

  it("returns false when fetch fails", async () => {
    mockFetch.mockRejectedValueOnce(new Error("offline"));
    await expect(checkPublicReachability()).resolves.toBe(false);
  });
});

describe("resolveConnectivity", () => {
  it("probes even when NetInfo reports connected", async () => {
    mockRefresh.mockResolvedValueOnce({ isConnected: true, isInternetReachable: false });
    mockCheckHealth.mockResolvedValueOnce(true);
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });
    await expect(resolveConnectivity()).resolves.toBe("online");
    expect(mockCheckHealth).toHaveBeenCalled();
  });

  it("does not ask Google when our API answers", async () => {
    mockRefresh.mockResolvedValueOnce({ isConnected: true, isInternetReachable: true });
    mockCheckHealth.mockResolvedValueOnce(true);
    await expect(resolveConnectivity()).resolves.toBe("online");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("is api_unreachable when the link is up, public internet works, and health fails", async () => {
    mockRefresh.mockResolvedValueOnce({ isConnected: true, isInternetReachable: true });
    mockCheckHealth.mockResolvedValueOnce(false);
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });
    await expect(resolveConnectivity()).resolves.toBe("api_unreachable");
  });

  it("is no_internet when the link is up but both probes fail", async () => {
    mockRefresh.mockResolvedValueOnce({ isConnected: true, isInternetReachable: true });
    mockCheckHealth.mockResolvedValueOnce(false);
    mockFetch.mockRejectedValueOnce(new Error("offline"));
    await expect(resolveConnectivity()).resolves.toBe("no_internet");
  });

  it("is online when NetInfo is stale offline but API health succeeds", async () => {
    mockRefresh.mockResolvedValueOnce({ isConnected: false, isInternetReachable: false });
    mockCheckHealth.mockResolvedValueOnce(true);
    mockFetch.mockRejectedValueOnce(new Error("blocked"));
    await expect(resolveConnectivity()).resolves.toBe("online");
  });

  it("is api_unreachable when API fails but public internet works", async () => {
    mockRefresh.mockResolvedValueOnce({ isConnected: false, isInternetReachable: false });
    mockCheckHealth.mockResolvedValueOnce(false);
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });
    await expect(resolveConnectivity()).resolves.toBe("api_unreachable");
  });

  it("recovers when NetInfo refresh hangs after reconnect", async () => {
    jest.useFakeTimers();
    try {
      mockRefresh.mockReturnValueOnce(new Promise(() => undefined));
      mockCheckHealth.mockResolvedValueOnce(true);
      mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });
      const result = resolveConnectivity();

      await jest.advanceTimersByTimeAsync(1_000);

      await expect(result).resolves.toBe("online");
    } finally {
      jest.useRealTimers();
    }
  });

  it("classifies hung API + successful public probe as api_unreachable", async () => {
    jest.useFakeTimers();
    try {
      mockRefresh.mockResolvedValueOnce({ isConnected: false, isInternetReachable: false });
      mockCheckHealth.mockReturnValueOnce(new Promise(() => undefined));
      mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });
      const result = resolveConnectivity();

      await jest.advanceTimersByTimeAsync(3_500);

      await expect(result).resolves.toBe("api_unreachable");
    } finally {
      jest.useRealTimers();
    }
  });

  it("settles no_internet when every reconnect probe hangs", async () => {
    jest.useFakeTimers();
    try {
      mockRefresh.mockReturnValueOnce(new Promise(() => undefined));
      mockCheckHealth.mockReturnValueOnce(new Promise(() => undefined));
      mockFetch.mockReturnValueOnce(new Promise(() => undefined));
      const result = resolveConnectivity();

      await jest.advanceTimersByTimeAsync(1_000);
      await jest.advanceTimersByTimeAsync(3_500);
      await jest.advanceTimersByTimeAsync(3_500);

      await expect(result).resolves.toBe("no_internet");
    } finally {
      jest.useRealTimers();
    }
  });

  it("is no_internet when NetInfo, API, and public probe all fail", async () => {
    mockRefresh.mockResolvedValueOnce({ isConnected: false, isInternetReachable: false });
    mockCheckHealth.mockResolvedValueOnce(false);
    mockFetch.mockRejectedValueOnce(new Error("offline"));
    await expect(resolveConnectivity()).resolves.toBe("no_internet");
  });
});
