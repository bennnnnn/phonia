import {
  ApiRequestError,
  apiUrl,
  authorizeNativeTransfer,
  fetchWithTimeout,
  fetchExportText,
  logoutSession,
  request,
  requestRaw,
  requestRevalidated,
  requestSse,
  setTokenRefreshHandler,
  setUnauthorizedHandler,
} from "@/lib/api/client";

jest.mock("@/lib/config", () => ({
  getApiUrl: () => "http://test.local",
}));

const mockGetRefreshToken = jest.fn();
const mockSetTokenPair = jest.fn();
let mockSessionGeneration = 0;
/** Each test is a sign-in of its own: a refresh one test made is not another's (`lastRefreshed`). */
let signIns = 0;
const mockRequireTokenSession = jest.fn();

jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => mockSessionGeneration,
  requireTokenSession: (...args: unknown[]) => mockRequireTokenSession(...args),
  SessionChangedError: class extends Error { constructor() { super("Session changed"); this.name = "SessionChangedError"; } },
  getRefreshToken: (...args: unknown[]) => mockGetRefreshToken(...args),
  setTokenPair: (...args: unknown[]) => mockSetTokenPair(...args),
}));



const mockFetch = jest.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => {
  mockFetch.mockReset();
  mockGetRefreshToken.mockReset();
  mockSetTokenPair.mockReset().mockResolvedValue(true);
  mockSessionGeneration = (signIns += 100);
  mockRequireTokenSession.mockReset();
  setUnauthorizedHandler(null);
  setTokenRefreshHandler(null);
});

describe("api client", () => {
  it("apiUrl prefixes paths with configured base", () => {
    expect(apiUrl("/chats")).toBe("http://test.local/chats");
  });

  it("request returns JSON on success", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ id: "chat-1" }),
    });

    const data = await request<{ id: string }>("/chats/1", "access-token");
    expect(data).toEqual({ id: "chat-1" });
    expect(mockFetch).toHaveBeenCalledWith(
      "http://test.local/chats/1",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer access-token",
        }),
      }),
    );
  });

  it("names every call with a fresh id the API accepts", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({}) });

    await request("/chats/1", "access-token");
    await request("/chats/2", "access-token");
    const ids = mockFetch.mock.calls.map(([, init]) => (init as RequestInit & { headers: Record<string, string> }).headers["X-Request-ID"]);
    expect(ids).toHaveLength(2);
    for (const id of ids) expect(id).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
    expect(ids[0]).not.toBe(ids[1]);
  });

  it("a refusal carries the id the API echoed", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      headers: { get: (name: string) => (name === "X-Request-ID" ? "echoed-id-1" : null) },
      text: async () => '{"detail":"boom"}',
    });

    await expect(request("/chats/1", "access-token")).rejects.toMatchObject({
      status: 500,
      requestId: "echoed-id-1",
    });
  });

  it("request refreshes on 401 and retries once", async () => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");
    mockSetTokenPair.mockResolvedValue(true);

    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: async () => "expired",
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: "new-access",
          refresh_token: "new-refresh",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ok: true }),
      });

    const onRefresh = jest.fn();
    setTokenRefreshHandler(onRefresh);

    const data = await request<{ ok: boolean }>("/users/me", "stale-token");
    expect(data).toEqual({ ok: true });
    expect(mockFetch).toHaveBeenCalledTimes(3);
    expect(mockSetTokenPair).toHaveBeenCalledWith("new-access", "new-refresh", mockSessionGeneration);
    // L2: onRefresh now also receives the user payload (undefined when the
    // refresh response omits it).
    expect(onRefresh).toHaveBeenCalledWith("new-access", undefined);
    expect(mockFetch.mock.calls[2][1]?.headers).toMatchObject({
      Authorization: "Bearer new-access",
    });
  });

  it("request calls onUnauthorized when refresh fails", async () => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");

    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: async () => "expired",
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: async () => "invalid refresh",
      });

    const onUnauthorized = jest.fn();
    setUnauthorizedHandler(onUnauthorized);

    await expect(request("/users/me", "stale-token")).rejects.toThrow("expired");
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("request throws ApiRequestError with HTTP status on failure", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      text: async () => '{"detail":"Image generation requires Pro"}',
    });

    const err = await request("/images/generate", "token").catch((error) => error);
    expect(err).toBeInstanceOf(ApiRequestError);
    expect(err).toMatchObject({
      name: "ApiRequestError",
      status: 403,
    });
  });

  it("single-flights concurrent refresh attempts", async () => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");
    mockSetTokenPair.mockResolvedValue(true);

    let resolveRefresh: (value: Response) => void;
    const refreshPromise = new Promise<Response>((resolve) => {
      resolveRefresh = resolve;
    });

    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "" })
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "" })
      .mockImplementationOnce(() => refreshPromise)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ a: 1 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ b: 2 }),
      });

    const p1 = request("/a", "t1");
    const p2 = request("/b", "t2");

    resolveRefresh!({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: "shared-access",
        refresh_token: "shared-refresh",
      }),
    } as Response);

    await expect(Promise.all([p1, p2])).resolves.toEqual([{ a: 1 }, { b: 2 }]);
    const refreshCalls = mockFetch.mock.calls.filter(
      (call) => call[0] === "http://test.local/auth/refresh",
    );
    expect(refreshCalls).toHaveLength(1);
  });

  it("fetchWithTimeout surfaces a friendly message on abort", async () => {
    const abortError = new Error("Aborted");
    abortError.name = "AbortError";
    mockFetch.mockRejectedValueOnce(abortError);

    await expect(
      fetchWithTimeout("http://test.local/auth/login", { method: "POST" }),
    ).rejects.toThrow("Could not reach the Recall server");
  });

  it("requestRaw returns the raw Response on success and adds Authorization", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: "stream",
    } as unknown as Response);

    const res = await requestRaw("/link-preview?url=x", "access-token");
    expect(res.ok).toBe(true);
    expect(mockFetch).toHaveBeenCalledWith(
      "http://test.local/link-preview?url=x",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer access-token",
        }),
      }),
    );
  });

  it("logoutSession sends the device's push token only when it has one", async () => {
    mockFetch.mockResolvedValue({ ok: true, status: 204 } as unknown as Response);
    await logoutSession("access", "refresh", "ExponentPushToken[phone]");
    await logoutSession("access", "refresh");
    const bodies = mockFetch.mock.calls.map((call) => JSON.parse(String(call[1]?.body)));
    expect(bodies).toEqual([
      { refresh_token: "refresh", expo_push_token: "ExponentPushToken[phone]" },
      { refresh_token: "refresh" },
    ]);
  });

  it("requestRaw omits Authorization when token is null", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 200 } as unknown as Response);
    await requestRaw("/link-preview?url=x", null);
    expect(mockFetch.mock.calls[0][1]?.headers).not.toHaveProperty("Authorization");
  });

  it("requestRaw refreshes on 401 and retries once with the fresh token", async () => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");
    mockSetTokenPair.mockResolvedValue(true);

    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: async () => "expired",
      } as unknown as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: "new-access",
          refresh_token: "new-refresh",
        }),
      } as unknown as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        body: "stream",
      } as unknown as Response);

    const res = await requestRaw("/link-preview?url=x", "stale-token");
    expect(res.ok).toBe(true);
    expect(mockFetch).toHaveBeenCalledTimes(3);
    // Third call (the retry) uses the refreshed token.
    expect(mockFetch.mock.calls[2][1]?.headers).toMatchObject({
      Authorization: "Bearer new-access",
    });
  });

  it("requestRaw calls onUnauthorized and returns the 401 response when refresh fails", async () => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");

    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: async () => "expired",
      } as unknown as Response)
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: async () => "invalid refresh",
      } as unknown as Response);

    const onUnauthorized = jest.fn();
    setUnauthorizedHandler(onUnauthorized);

    const res = await requestRaw("/link-preview?url=x", "stale-token");
    expect(res.ok).toBe(false);
    expect(res.status).toBe(401);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("requestSse sets SSE headers (Accept + Content-Type) and POSTs the body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: "stream",
    } as unknown as Response);

    await requestSse("/chats/c1/messages/stream", "tok", { content: "hi" });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [, init] = mockFetch.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: "Bearer tok",
    });
    expect(init?.body).toBe(JSON.stringify({ content: "hi" }));
  });
});

describe("session recovery", () => {
  it.each([429, 500, 503])("preserves sign-in when refresh returns %s", async (status) => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "expired" })
      .mockResolvedValueOnce({ ok: false, status, text: async () => "Try again later" });
    const unauthorized = jest.fn();
    setUnauthorizedHandler(unauthorized);
    await expect(request("/auth/me", "old-access")).rejects.toThrow("Try again later");
    expect(unauthorized).not.toHaveBeenCalled();
    expect(mockSetTokenPair).not.toHaveBeenCalled();
  });

  it("preserves sign-in when refresh cannot reach the server", async () => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "expired" })
      .mockRejectedValueOnce(new Error("Network request failed"));
    const unauthorized = jest.fn();
    setUnauthorizedHandler(unauthorized);
    await expect(request("/auth/me", "old-access")).rejects.toThrow("Network request failed");
    expect(unauthorized).not.toHaveBeenCalled();
  });

  it("notifies unauthorized when the raw request retry also returns401", async () => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");
    mockSetTokenPair.mockResolvedValue(true);
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockResolvedValueOnce({
        ok: true, status: 200,
        json: async () => ({ access_token: "new-access", refresh_token: "new-refresh" }),
      })
      .mockResolvedValueOnce({ ok: false, status: 401 });
    const unauthorized = jest.fn();
    setUnauthorizedHandler(unauthorized);
    const response = await requestRaw("/chats/c1/messages/stream", "old-access");
    expect(response.status).toBe(401);
    expect(unauthorized).toHaveBeenCalledTimes(1);
  });

  it("does not retry a canceled request after token refresh finishes", async () => {
    const signal = new AbortController();
    mockGetRefreshToken.mockResolvedValue("refresh-token");
    mockSetTokenPair.mockResolvedValue(true);
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockImplementationOnce(async () => {
        signal.abort();
        return {
          ok: true, status: 200,
          json: async () => ({ access_token: "new-access", refresh_token: "new-refresh" }),
        };
      })
      .mockResolvedValueOnce({ ok: true, status: 200 });
    await expect(requestRaw("/chats/c1/messages/stream", "old-access", { signal: signal.signal }))
      .rejects.toMatchObject({ name: "AbortError" });
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}

it("does not revoke a new session when an old request finally returns401", async () => {
  const response = deferred<Response>();
  mockFetch.mockReturnValueOnce(response.promise);
  const unauthorized = jest.fn();
  setUnauthorizedHandler(unauthorized);
  const pending = requestRaw("/auth/me", "old-access");
  mockSessionGeneration++;
  response.resolve({ ok: false, status: 401 } as Response);
  await expect(pending).rejects.toMatchObject({ name: "SessionChangedError" });
  expect(unauthorized).not.toHaveBeenCalled();
  expect(mockGetRefreshToken).not.toHaveBeenCalled();
});

it("does not save or publish an old refresh after sign-out", async () => {
  const refresh = deferred<Response>();
  const started = deferred<void>();
  mockGetRefreshToken.mockResolvedValue("refresh-token");
  mockFetch
    .mockResolvedValueOnce({ ok: false, status: 401 })
    .mockImplementationOnce(() => { started.resolve(); return refresh.promise; });
  const onRefresh = jest.fn();
  const unauthorized = jest.fn();
  setTokenRefreshHandler(onRefresh);
  setUnauthorizedHandler(unauthorized);
  const pending = requestRaw("/auth/me", "old-access");
  await started.promise;
  mockSessionGeneration++;
  refresh.resolve({
    ok: true, status: 200,
    json: async () => ({ access_token: "late-access", refresh_token: "late-refresh" }),
  } as Response);
  await expect(pending).rejects.toMatchObject({ name: "SessionChangedError" });
  expect(mockSetTokenPair).not.toHaveBeenCalled();
  expect(onRefresh).not.toHaveBeenCalled();
  expect(unauthorized).not.toHaveBeenCalled();
});

it("does not share an old account's in-flight refresh with the next account", async () => {
  const firstRefresh = deferred<Response>();
  const started = deferred<void>();
  mockGetRefreshToken.mockResolvedValueOnce("refresh-a").mockResolvedValueOnce("refresh-b");
  mockFetch
    .mockResolvedValueOnce({ ok: false, status: 401 })
    .mockImplementationOnce(() => { started.resolve(); return firstRefresh.promise; })
    .mockResolvedValueOnce({ ok: false, status: 401 })
    .mockResolvedValueOnce({
      ok: true, status: 200,
      json: async () => ({ access_token: "access-b2", refresh_token: "refresh-b2" }),
    })
    .mockResolvedValueOnce({ ok: true, status: 200 });
  const oldRequest = requestRaw("/auth/me", "access-a");
  const oldOutcome = oldRequest.catch((error: unknown) => error);
  await started.promise;
  mockSessionGeneration++;
  await expect(requestRaw("/auth/me", "access-b")).resolves.toMatchObject({ status: 200 });
  firstRefresh.resolve({ ok: false, status: 401 } as Response);
  await expect(oldOutcome).resolves.toMatchObject({ name: "SessionChangedError" });
  expect(mockSetTokenPair).toHaveBeenCalledTimes(1);
  expect(mockSetTokenPair).toHaveBeenCalledWith("access-b2", "refresh-b2", mockSessionGeneration);
});

it("rejects malformed refresh data without signing out or saving undefined tokens", async () => {
  mockGetRefreshToken.mockResolvedValue("refresh-token");
  mockFetch
    .mockResolvedValueOnce({ ok: false, status: 401 })
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ error: "proxy failure" }) });
  const unauthorized = jest.fn();
  setUnauthorizedHandler(unauthorized);
  await expect(requestRaw("/auth/me", "old-access")).rejects.toThrow("invalid sign-in response");
  expect(mockSetTokenPair).not.toHaveBeenCalled();
  expect(unauthorized).not.toHaveBeenCalled();
});

it("surfaces a refreshed token persistence failure without signing out", async () => {
  mockGetRefreshToken.mockResolvedValue("refresh-token");
  mockSetTokenPair.mockRejectedValueOnce(new Error("Secure storage unavailable"));
  mockFetch
    .mockResolvedValueOnce({ ok: false, status: 401 })
    .mockResolvedValueOnce({
      ok: true, status: 200,
      json: async () => ({ access_token: "new-access", refresh_token: "new-refresh" }),
    });
  const unauthorized = jest.fn();
  const onRefresh = jest.fn();
  setUnauthorizedHandler(unauthorized);
  setTokenRefreshHandler(onRefresh);
  await expect(requestRaw("/auth/me", "old-access")).rejects.toThrow("Secure storage unavailable");
  expect(unauthorized).not.toHaveBeenCalled();
  expect(onRefresh).not.toHaveBeenCalled();
});

it("honors an already aborted signal without starting a request", async () => {
  const controller = new AbortController();
  controller.abort();
  await expect(requestRaw("/auth/me", "access", { signal: controller.signal }))
    .rejects.toMatchObject({ name: "AbortError" });
  expect(mockFetch).not.toHaveBeenCalled();
});

it("does not send or replay a retained previous-account token after switching accounts", async () => {
  mockSessionGeneration = 1;
  mockRequireTokenSession.mockImplementationOnce(() => { throw new Error("Session changed"); });
  await expect(requestRaw("/todos", "old-account-token", { method: "POST" }))
    .rejects.toThrow("Session changed");
  expect(mockFetch).not.toHaveBeenCalled();
  expect(mockGetRefreshToken).not.toHaveBeenCalled();
});

it("keeps Stop connected to the SSE fetch after response headers arrive", async () => {
  const controller = new AbortController();
  mockFetch.mockResolvedValueOnce({ ok: true, status: 200, body: {} });
  await requestSse("/chats/c1/messages/stream", "access", {}, controller.signal);
  const fetchSignal = mockFetch.mock.calls[0][1].signal as AbortSignal;
  expect(fetchSignal.aborted).toBe(false);
  controller.abort();
  expect(fetchSignal.aborted).toBe(true);
});

it.each(["json", "export"])("discards an old account's %s body that finishes after sign-out", async (kind) => {
  const body = deferred<never>();
  const decoding = deferred<void>();
  const decode = () => { decoding.resolve(); return body.promise; };
  mockFetch.mockResolvedValueOnce({ ok: true, status: 200, json: decode, text: decode });
  const pending = kind === "json" ? request("/auth/me", "access") : fetchExportText("access");
  await decoding.promise;
  mockSessionGeneration++;
  body.resolve("previous account data" as never);
  await expect(pending).rejects.toMatchObject({ name: "SessionChangedError" });
});


it("SSE headers timeout aborts the fetch without marking the caller as canceled", async () => {
  jest.useFakeTimers();
  try {
    const caller = new AbortController();
    mockFetch.mockImplementationOnce((_url, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(Object.assign(new Error("timeout"), { name: "AbortError" })));
    }));
    const outcome = requestSse("/chats/c1/messages/stream", "access", {}, caller.signal)
      .catch((error: unknown) => error);
    await jest.advanceTimersByTimeAsync(30_000);
    await expect(outcome).resolves.toMatchObject({ name: "AbortError" });
    expect(caller.signal.aborted).toBe(false);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  } finally {
    jest.useRealTimers();
  }
});

describe("authorizeNativeTransfer", () => {
  it("refreshes once on 401 and resends with the fresh token", async () => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ access_token: "new-access", refresh_token: "new-refresh" }),
    } as unknown as Response);
    const send = jest.fn<Promise<number>, [Record<string, string>]>()
      .mockResolvedValueOnce(401)
      .mockResolvedValueOnce(200);

    await expect(authorizeNativeTransfer("stale-token", send)).resolves.toBe(200);
    expect(send.mock.calls.map(([headers]) => headers.Authorization)).toEqual([
      "Bearer stale-token",
      "Bearer new-access",
    ]);
  });

  it("signs out once when the refreshed token is refused too", async () => {
    mockGetRefreshToken.mockResolvedValue(null);
    const onUnauthorized = jest.fn();
    setUnauthorizedHandler(onUnauthorized);
    const send = jest.fn(async () => 401);
    await expect(authorizeNativeTransfer("stale-token", send)).resolves.toBe(401);
    expect(send).toHaveBeenCalledTimes(1);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("sends no credentials without a token, only the call's id", async () => {
    const send = jest.fn(async (_headers: Record<string, string>) => 200);
    await authorizeNativeTransfer(null, send);
    const [[headers]] = send.mock.calls;
    expect(Object.keys(headers)).toEqual(["X-Request-ID"]);
    expect(headers["X-Request-ID"]).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
  });
});

describe("deadlines past the headers (NET-17)", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("rejects a request whose body never finishes at its deadline", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 200, json: () => new Promise(() => undefined) });
    const outcome = request("/auth/me", "access", undefined, true, 5_000).catch((error: unknown) => error);
    await jest.advanceTimersByTimeAsync(4_999);
    let settled = false;
    void outcome.then(() => { settled = true; });
    await jest.advanceTimersByTimeAsync(0);
    expect(settled).toBe(false);
    await jest.advanceTimersByTimeAsync(1);
    await expect(outcome).resolves.toMatchObject({ name: "AbortError" });
  });

  it("rejects an export whose body never finishes", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 200, text: () => new Promise(() => undefined) });
    const outcome = fetchExportText("access").catch((error: unknown) => error);
    await jest.advanceTimersByTimeAsync(120_000);
    await expect(outcome).resolves.toMatchObject({ name: "AbortError" });
  });

  it("fails a stalled refresh for every request behind it, and the next request starts a new one", async () => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "" })
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "" })
      // The refresh's headers arrive; its body never does.
      .mockResolvedValueOnce({ ok: true, status: 200, json: () => new Promise(() => undefined) });
    const first = request("/a", "t1", undefined, true, 60_000).catch((error: unknown) => error);
    const second = request("/b", "t2", undefined, true, 60_000).catch((error: unknown) => error);
    await jest.advanceTimersByTimeAsync(15_000);
    await expect(first).resolves.toMatchObject({ message: expect.stringContaining("Could not reach") });
    await expect(second).resolves.toMatchObject({ message: expect.stringContaining("Could not reach") });

    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "" })
      .mockResolvedValueOnce({
        ok: true, status: 200,
        json: async () => ({ access_token: "new-access", refresh_token: "new-refresh" }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ok: 1 }) });
    await expect(request("/c", "t3")).resolves.toEqual({ ok: 1 });
    const refreshes = mockFetch.mock.calls.filter(([url]) => url === "http://test.local/auth/refresh");
    expect(refreshes).toHaveLength(2);
  });

  it("stops waiting for another request's refresh when its own caller aborts", async () => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");
    const refresh = deferred<Response>();
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "" })
      .mockImplementationOnce(() => refresh.promise);
    const caller = new AbortController();
    const outcome = request("/a", "t1", { signal: caller.signal }).catch((error: unknown) => error);
    await jest.advanceTimersByTimeAsync(0);
    caller.abort();
    await expect(outcome).resolves.toMatchObject({ name: "AbortError" });
  });
});


describe("revalidated reads (NET-16)", () => {
  const withEtag = (body: unknown, etag: string) => ({
    ok: true, status: 200, headers: { get: (name: string) => (name === "etag" ? etag : null) },
    json: async () => body,
  });

  it("sends the kept ETag back and answers a 304 with the kept body", async () => {
    mockFetch
      .mockResolvedValueOnce(withEtag({ items: [1] }, 'W/"one"'))
      .mockResolvedValueOnce({ ok: false, status: 304, headers: { get: () => 'W/"one"' } });
    await expect(requestRevalidated("/todos/page?x=1", "access")).resolves.toEqual({ items: [1] });
    await expect(requestRevalidated("/todos/page?x=1", "access")).resolves.toEqual({ items: [1] });
    expect(mockFetch.mock.calls[0][1].headers["If-None-Match"]).toBeUndefined();
    expect(mockFetch.mock.calls[1][1].headers["If-None-Match"]).toBe('W/"one"');
  });

  it("keeps the new body when the list changed", async () => {
    mockFetch
      .mockResolvedValueOnce(withEtag({ items: [1] }, 'W/"one"'))
      .mockResolvedValueOnce(withEtag({ items: [2] }, 'W/"two"'))
      .mockResolvedValueOnce({ ok: false, status: 304, headers: { get: () => 'W/"two"' } });
    await requestRevalidated("/chats", "access");
    await expect(requestRevalidated("/chats", "access")).resolves.toEqual({ items: [2] });
    await expect(requestRevalidated("/chats", "access")).resolves.toEqual({ items: [2] });
    expect(mockFetch.mock.calls[2][1].headers["If-None-Match"]).toBe('W/"two"');
  });

  it("never offers another sign-in's body", async () => {
    mockFetch.mockResolvedValueOnce(withEtag({ items: ["a"] }, 'W/"a"'));
    await requestRevalidated("/chats?who", "access");
    mockSessionGeneration += 1;
    mockFetch.mockResolvedValueOnce(withEtag({ items: ["b"] }, 'W/"b"'));
    await expect(requestRevalidated("/chats?who", "access")).resolves.toEqual({ items: ["b"] });
    expect(mockFetch.mock.calls[1][1].headers["If-None-Match"]).toBeUndefined();
  });
});
