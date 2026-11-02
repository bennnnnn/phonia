import { request, requestRaw, requestSse } from "@/lib/api/client";
import { onConnectionAnswered, onConnectionFailure } from "@/lib/api/connectionFailures";

jest.mock("@/lib/config", () => ({
  getApiUrl: () => "http://test.local",
}));

let mockSessionGeneration = 0;
const mockGetRefreshToken = jest.fn();

jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => mockSessionGeneration,
  requireTokenSession: () => {},
  SessionChangedError: class extends Error { constructor() { super("Session changed"); this.name = "SessionChangedError"; } },
  getRefreshToken: (...args: unknown[]) => mockGetRefreshToken(...args),
  setTokenPair: async () => true,
}));

const mockFetch = jest.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

const answer = (status: number) => ({ ok: status < 400, status, text: async () => "", json: async () => ({}) });
const networkError = () => new TypeError("Network request failed");

let reported = 0;
let stop: () => void = () => {};

beforeEach(() => {
  mockFetch.mockReset();
  mockGetRefreshToken.mockReset();
  mockSessionGeneration += 100;
  reported = 0;
  stop = onConnectionFailure(() => { reported += 1; });
});
afterEach(() => stop());

describe("a request that finds no API asks for a connection check", () => {
  it("reports a request that gets no answer, once", async () => {
    mockFetch.mockRejectedValueOnce(networkError());
    await expect(request("/todos/page", "access")).rejects.toThrow("Network request failed");
    expect(reported).toBe(1);
  });

  it.each([502, 503, 504])("reports a %s, read or stream", async (status) => {
    mockFetch.mockResolvedValueOnce(answer(status)).mockResolvedValueOnce(answer(status));
    await expect(request("/chats", "access")).rejects.toMatchObject({ status });
    await expect(requestSse("/chats/1/messages/stream", "access", {})).resolves.toMatchObject({ status });
    expect(reported).toBe(2);
  });

  it.each([400, 401, 403, 404, 409, 422, 429, 500])("does not report a %s", async (status) => {
    mockFetch.mockResolvedValue(answer(status));
    await requestRaw("/chats", "access", undefined, false);
    expect(reported).toBe(0);
  });

  it("does not report an answer", async () => {
    mockFetch.mockResolvedValueOnce(answer(200));
    await request("/chats", "access");
    expect(reported).toBe(0);
  });

  it("does not report a request its caller cancels", async () => {
    const caller = new AbortController();
    mockFetch.mockImplementationOnce((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(Object.assign(new Error("Aborted"), { name: "AbortError" })));
    }));
    const outcome = request("/chats", "access", { signal: caller.signal }).catch((error: unknown) => error);
    await Promise.resolve();
    caller.abort();
    await expect(outcome).resolves.toMatchObject({ name: "AbortError" });
    expect(reported).toBe(0);
  });

  it("does not report a fetch that fails after its caller cancelled it", async () => {
    const caller = new AbortController();
    mockFetch.mockImplementationOnce((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(networkError()));
    }));
    const outcome = requestRaw("/chats", "access", { signal: caller.signal }).catch((error: unknown) => error);
    await Promise.resolve();
    caller.abort();
    await outcome;
    expect(reported).toBe(0);
  });

  it("does not report a request that runs past its deadline", async () => {
    mockFetch.mockImplementationOnce((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(networkError()));
    }));
    await expect(request("/chats", "access", undefined, true, 10)).rejects.toMatchObject({ name: "AbortError" });
    expect(reported).toBe(0);
  });

  it("does not report a request of an account signed out while it was out", async () => {
    mockFetch.mockImplementationOnce(async () => {
      mockSessionGeneration += 1;
      throw networkError();
    });
    await expect(requestRaw("/chats", "access")).rejects.toBeDefined();
    mockFetch.mockImplementationOnce(async () => {
      mockSessionGeneration += 1;
      return answer(503);
    });
    await expect(requestRaw("/chats", "access")).rejects.toBeDefined();
    expect(reported).toBe(0);
  });

  it("reports a token refresh that gets no answer", async () => {
    mockGetRefreshToken.mockResolvedValue("refresh-token");
    mockFetch.mockResolvedValueOnce(answer(401)).mockRejectedValueOnce(networkError());
    await expect(request("/auth/me", "old-access")).rejects.toThrow("Network request failed");
    expect(reported).toBe(1);
  });
});

describe("a request our API answers says when it was sent", () => {
  let answers: number[] = [];
  let stopAnswers: () => void = () => {};
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(1_000_000);
    answers = [];
    stopAnswers = onConnectionAnswered((sentAt) => { answers.push(sentAt); });
  });
  afterEach(() => {
    stopAnswers();
    jest.useRealTimers();
  });

  /** The server answers `status` 5 s after the request is sent. */
  const answerLater = (status: number) => mockFetch.mockImplementationOnce(async () => {
    jest.setSystemTime(Date.now() + 5_000);
    return answer(status);
  });

  it.each([200, 204, 304])("reports a %s, with the time it was sent", async (status) => {
    answerLater(status);
    await requestRaw("/chats", "access", undefined, false);
    expect(answers).toEqual([1_000_000]);
  });

  it.each([401, 404, 429, 500, 503])("reports no answer for a %s", async (status) => {
    answerLater(status);
    await requestRaw("/chats", "access", undefined, false);
    expect(answers).toEqual([]);
  });

  it("reports no answer for a request that got none", async () => {
    mockFetch.mockRejectedValueOnce(networkError());
    await expect(requestRaw("/chats", "access")).rejects.toThrow("Network request failed");
    expect(answers).toEqual([]);
  });
});
