const mockStore = new Map<string, string>();
const mockLogoutSession = jest.fn<Promise<boolean>, [string, string | null, string | null]>();
const mockGetToken = jest.fn<Promise<string | null>, []>();
let mockForeground: ((state: string) => void) | null = null;
let mockAnswered: (() => void) | null = null;

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(async (key: string) => mockStore.get(key) ?? null),
  setItemAsync: jest.fn(async (key: string, value: string) => {
    mockStore.set(key, value);
  }),
  deleteItemAsync: jest.fn(async (key: string) => {
    mockStore.delete(key);
  }),
}));
jest.mock("@/lib/foregroundRefresh", () => ({
  onAppStateChange: (listener: (state: string) => void) => {
    mockForeground = listener;
    return () => {
      mockForeground = null;
    };
  },
}));
jest.mock("@/lib/api/connectionFailures", () => ({
  onConnectionAnswered: (listener: () => void) => {
    mockAnswered = listener;
    return () => {
      mockAnswered = null;
    };
  },
}));
jest.mock("@/lib/sentry", () => ({ reportFailure: jest.fn() }));
jest.mock("@/lib/api/client", () => ({
  logoutSession: (...args: [string, string | null, string | null]) => mockLogoutSession(...args),
}));
jest.mock("@/lib/auth", () => ({ getToken: () => mockGetToken() }));

import {
  endServerSession,
  PENDING_LOGOUT_MAX_AGE_MS,
  resetPendingLogoutsForTest,
  retryPendingLogouts,
  watchPendingLogouts,
  type ServerLogout,
} from "@/lib/pendingLogout";

const KEY = "phonia_pending_logouts_v1";
const LOGOUT_A: ServerLogout = { accessToken: "access-a", refreshToken: "refresh-a", pushToken: "Expo[phone]" };
const LOGOUT_B: ServerLogout = { accessToken: "access-b", refreshToken: "refresh-b", pushToken: null };

function owed(): string[] {
  const raw = mockStore.get(KEY);
  return raw ? (JSON.parse(raw) as ServerLogout[]).map((entry) => entry.accessToken) : [];
}

async function flush(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
}

beforeEach(() => {
  mockStore.clear();
  mockLogoutSession.mockReset();
  mockGetToken.mockReset().mockResolvedValue(null);
  mockForeground = null;
  mockAnswered = null;
  resetPendingLogoutsForTest();
});

describe("endServerSession", () => {
  it("crosses the logout off once the server has it", async () => {
    mockLogoutSession.mockResolvedValue(true);
    await endServerSession(Promise.resolve(LOGOUT_A));
    expect(mockLogoutSession).toHaveBeenCalledWith("access-a", "refresh-a", "Expo[phone]");
    expect(owed()).toEqual([]);
  });

  it("keeps a logout the server did not hear (offline)", async () => {
    mockLogoutSession.mockResolvedValue(false);
    await endServerSession(Promise.resolve(LOGOUT_A));
    expect(owed()).toEqual(["access-a"]);
  });

  it("writes the logout down before it is sent, so a killed app still owes it", async () => {
    let seenWhileSending: string[] = [];
    mockLogoutSession.mockImplementation(async () => {
      seenWhileSending = owed();
      return true;
    });
    await endServerSession(Promise.resolve(LOGOUT_A));
    expect(seenWhileSending).toEqual(["access-a"]);
  });
});

describe("retryPendingLogouts", () => {
  async function owe(...logouts: ServerLogout[]): Promise<void> {
    mockLogoutSession.mockResolvedValue(false);
    for (const logout of logouts) await endServerSession(Promise.resolve(logout));
    mockLogoutSession.mockReset();
  }

  it("sends a signed-out phone's owed logout with its push token, read now when it was not known", async () => {
    await owe(LOGOUT_A, LOGOUT_B);
    mockLogoutSession.mockResolvedValue(true);
    await retryPendingLogouts(async () => "Expo[now]");
    expect(mockLogoutSession.mock.calls).toEqual([
      ["access-a", "refresh-a", "Expo[phone]"],
      ["access-b", "refresh-b", "Expo[now]"],
    ]);
    expect(owed()).toEqual([]);
  });

  it("sends no push token once someone has signed in again: the device's token is theirs", async () => {
    await owe(LOGOUT_A);
    mockGetToken.mockResolvedValue("access-new");
    mockLogoutSession.mockResolvedValue(true);
    await retryPendingLogouts(async () => "Expo[now]");
    expect(mockLogoutSession).toHaveBeenCalledWith("access-a", "refresh-a", null);
    expect(owed()).toEqual([]);
  });

  it("stops at the first logout that does not reach the server and keeps the rest", async () => {
    await owe(LOGOUT_A, LOGOUT_B);
    mockLogoutSession.mockResolvedValue(false);
    await retryPendingLogouts(async () => null);
    expect(mockLogoutSession).toHaveBeenCalledTimes(1);
    expect(owed()).toEqual(["access-a", "access-b"]);
  });

  it("drops a logout older than the refresh token's life without sending it", async () => {
    const now = Date.now();
    const spy = jest.spyOn(Date, "now").mockReturnValue(now);
    await owe(LOGOUT_A);
    spy.mockReturnValue(now + PENDING_LOGOUT_MAX_AGE_MS + 1);
    await retryPendingLogouts(async () => null);
    spy.mockRestore();
    expect(mockLogoutSession).not.toHaveBeenCalled();
    expect(owed()).toEqual([]);
  });

  it("ignores a record it cannot read", async () => {
    mockStore.set(KEY, "{not json");
    await retryPendingLogouts(async () => null);
    expect(mockLogoutSession).not.toHaveBeenCalled();
  });
});

describe("watchPendingLogouts", () => {
  it("retries at start, on a return to the app and when our API answers again", async () => {
    mockLogoutSession.mockResolvedValue(false);
    await endServerSession(Promise.resolve(LOGOUT_A));
    mockLogoutSession.mockClear();

    const stop = watchPendingLogouts(async () => null);
    await flush();
    expect(mockLogoutSession).toHaveBeenCalledTimes(1);

    mockForeground?.("background");
    await flush();
    expect(mockLogoutSession).toHaveBeenCalledTimes(1);
    mockForeground?.("active");
    await flush();
    expect(mockLogoutSession).toHaveBeenCalledTimes(2);
    expect(owed()).toEqual(["access-a"]);

    mockLogoutSession.mockResolvedValue(true);
    mockAnswered?.();
    await flush();
    expect(mockLogoutSession).toHaveBeenCalledTimes(3);
    expect(owed()).toEqual([]);

    // Nothing owed: a later return reads nothing and sends nothing.
    mockForeground?.("active");
    mockAnswered?.();
    await flush();
    expect(mockLogoutSession).toHaveBeenCalledTimes(3);
    stop();
    expect(mockForeground).toBeNull();
    expect(mockAnswered).toBeNull();
  });
});
