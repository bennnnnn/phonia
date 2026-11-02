import type { ErrorEvent } from "@sentry/react-native";

import { redactSecrets, scrubBreadcrumb, scrubSentryEvent } from "@/lib/sentry";

const mockSdkLoads: string[] = [];

jest.mock("@sentry/react-native", () => {
  mockSdkLoads.push("@sentry/react-native");
  return {
    init: jest.fn(),
    captureException: jest.fn(),
    captureMessage: jest.fn(),
    addBreadcrumb: jest.fn(),
  };
});

jest.mock("@/lib/config", () => ({ getApiUrl: () => "https://api.recall.test" }));

const JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig_part_here";

describe("mobile Sentry scrubbing (O10.1)", () => {
  it("drops request bodies, query strings, cookies, auth headers, extras and user fields", () => {
    const event = {
      request: {
        url: "https://api.example.com/chats/1/messages?token=abc",
        query_string: "token=abc",
        data: '{"content":"my private question"}',
        cookies: { session: "s" },
        headers: { Authorization: `Bearer ${JWT}`, Accept: "application/json" },
      },
      extra: { prompt: "my private question" },
      user: { id: "u1", email: "a@b.c", ip_address: "1.2.3.4" },
      exception: { values: [{ type: "Error", value: `Request failed with Bearer ${JWT}` }] },
      breadcrumbs: [
        { category: "console", message: "draft: my private question" },
        {
          category: "fetch",
          data: { method: "POST", url: "https://api.example.com/x?y=1", status_code: 500, body: "text" },
        },
        { category: "navigation", data: { from: "/", to: "/memory" } },
      ],
    } as unknown as ErrorEvent;

    const scrubbed = scrubSentryEvent(event);
    const text = JSON.stringify(scrubbed);

    expect(text).not.toContain("my private question");
    expect(text).not.toContain(JWT);
    expect(text).not.toContain("token=abc");
    expect(text).not.toContain("a@b.c");
    expect(scrubbed?.request?.headers?.Authorization).toBe("[REDACTED]");
    expect(scrubbed?.request?.url).toBe("https://api.example.com/chats/1/messages");
    expect(scrubbed?.user).toEqual({ id: "u1" });
    expect(scrubbed?.breadcrumbs).toEqual([
      { category: "fetch", data: { method: "POST", url: "https://api.example.com/x", status_code: 500 } },
      { category: "navigation", data: { from: "/", to: "/memory" } },
    ]);
  });

  it("redacts tokens and Live Talk secrets, and bounds a long error text", () => {
    expect(redactSecrets("key ek_abcdefghijkl and sk_live_123456789")).toBe(
      "key [REDACTED] and [REDACTED]",
    );
    expect(redactSecrets("x".repeat(400))).toHaveLength(301);
  });

  it("drops console breadcrumbs before they are recorded", () => {
    expect(scrubBreadcrumb({ category: "console", message: "hello" })).toBeNull();
  });

  it("tags a refused call's report with its id, and nothing that is no id", () => {
    const tagged = scrubSentryEvent({ tags: { area: "x" } } as unknown as ErrorEvent, {
      originalException: { requestId: "m1abc-0123456789abcdef" },
    });
    expect(tagged?.tags).toEqual({ area: "x", request_id: "m1abc-0123456789abcdef" });
    const untagged = scrubSentryEvent({} as unknown as ErrorEvent, {
      originalException: { requestId: "my private question" },
    });
    expect(untagged?.tags).toBeUndefined();
    expect(scrubSentryEvent({} as unknown as ErrorEvent, { originalException: null })?.tags).toBeUndefined();
  });

  it("keeps a failed call's id on its crumb", () => {
    const crumb = scrubBreadcrumb({
      category: "api",
      data: { method: "GET", url: "/search", status_code: 500, request_id: "abc-1", body: "q" },
    });
    expect(crumb?.data).toEqual({ method: "GET", url: "/search", status_code: 500, request_id: "abc-1" });
  });
});

describe("error-boundary capture", () => {
  const originalDsn = process.env.EXPO_PUBLIC_SENTRY_DSN;
  afterEach(() => {
    process.env.EXPO_PUBLIC_SENTRY_DSN = originalDsn;
    jest.resetModules();
  });

  type SdkMock = {
    init: jest.Mock;
    captureException: jest.Mock;
    captureMessage: jest.Mock;
    addBreadcrumb: jest.Mock;
  };

  function freshSentry() {
    jest.resetModules();
    mockSdkLoads.length = 0;
    const mod = jest.requireActual<typeof import("@/lib/sentry")>("@/lib/sentry");
    // The module the init loads, from the same registry.
    const sdk = () => jest.requireMock<SdkMock>("@sentry/react-native");
    return { mod, sdk };
  }

  it("leaves a failed call's crumb without its query, and never fails the call", async () => {
    (globalThis as unknown as { __DEV__: boolean }).__DEV__ = false;
    process.env.EXPO_PUBLIC_SENTRY_DSN = "https://key@sentry.example.com/1";
    const { mod, sdk } = freshSentry();
    await mod.initMobileSentry();
    mod.noteApiFailure("GET", "/search?q=my private question", 503, "abc-1");
    expect(sdk().addBreadcrumb).toHaveBeenCalledWith(
      expect.objectContaining({
        category: "api",
        data: { method: "GET", url: "/search", status_code: 503, request_id: "abc-1" },
      }),
    );
    sdk().addBreadcrumb.mockImplementation(() => {
      throw new Error("sdk broke");
    });
    expect(() => mod.noteApiFailure("GET", "/chats", null, "abc-2")).not.toThrow();
  });

  it("reports nothing when Sentry is not configured", async () => {
    delete process.env.EXPO_PUBLIC_SENTRY_DSN;
    const { mod } = freshSentry();
    await mod.initMobileSentry();
    mod.reportBoundaryError("markdown", new Error("render failed"), "in MarkdownContent");
    await Promise.resolve();
    expect(mockSdkLoads).toEqual([]);
  });

  it("loads the SDK only in the deferred init, then captures a boundary crash", async () => {
    (globalThis as unknown as { __DEV__: boolean }).__DEV__ = false;
    process.env.EXPO_PUBLIC_SENTRY_DSN = "https://key@sentry.example.com/1";
    const { mod, sdk } = freshSentry();
    expect(mockSdkLoads).toEqual([]);

    await mod.initMobileSentry();
    expect(mockSdkLoads).toEqual(["@sentry/react-native"]);
    expect(sdk().init).toHaveBeenCalledWith(
      expect.objectContaining({ sendDefaultPii: false, beforeSend: expect.any(Function) }),
    );
    // Trace headers go to our API's URLs only (sentryTraceHeaders.test.tsx runs the SDK).
    const targets: RegExp[] = sdk().init.mock.calls[0][0].tracePropagationTargets;
    const traced = (url: string) => targets.some((target) => target.test(url));
    expect(["https://api.recall.test", "https://api.recall.test/chats?limit=40"].every(traced)).toBe(true);
    expect(["https://api.openai.com/v1/realtime/calls", "https://api.recall.test.evil.example/"].some(traced)).toBe(false);
    const error = new Error("render failed");
    mod.reportBoundaryError("message_row", error, "\n    in MessageBubble");
    expect(sdk().captureException).toHaveBeenCalledWith(error, {
      tags: { boundary: "message_row" },
      contexts: { react: { componentStack: "\n    in MessageBubble" } },
    });
  });

  it("keeps a crash reported before the SDK is up and sends it once it starts", async () => {
    process.env.EXPO_PUBLIC_SENTRY_DSN = "https://key@sentry.example.com/1";
    const { mod, sdk } = freshSentry();
    const early = new Error("early render failure");
    mod.reportBoundaryError("markdown", early, null);
    expect(mockSdkLoads).toEqual([]);

    await Promise.all([mod.initMobileSentry(), mod.initMobileSentry()]);
    expect(sdk().init).toHaveBeenCalledTimes(1);
    expect(sdk().captureException).toHaveBeenCalledTimes(1);
    expect(sdk().captureException).toHaveBeenCalledWith(early, {
      tags: { boundary: "markdown" },
      contexts: undefined,
    });
  });

  it("tags a screen's crash with its route file, not the values in it", async () => {
    process.env.EXPO_PUBLIC_SENTRY_DSN = "https://key@sentry.example.com/1";
    const { mod, sdk } = freshSentry();
    await mod.initMobileSentry();
    const error = new Error("screen render failed");
    mod.reportBoundaryError("screen", error, null, "memory/[key]");
    expect(sdk().captureException).toHaveBeenCalledWith(error, {
      tags: { boundary: "screen", screen: "memory/[key]" },
      contexts: undefined,
    });
  });

  it("keeps only the first few crashes of a loop before init", async () => {
    process.env.EXPO_PUBLIC_SENTRY_DSN = "https://key@sentry.example.com/1";
    const { mod, sdk } = freshSentry();
    for (let i = 0; i < 25; i += 1) mod.reportBoundaryError("message_row", new Error(`loop ${i}`));
    await mod.initMobileSentry();
    expect(sdk().captureException).toHaveBeenCalledTimes(10);
  });
});

describe("a stored sign-in cleared at launch", () => {
  const originalDsn = process.env.EXPO_PUBLIC_SENTRY_DSN;
  afterEach(() => {
    process.env.EXPO_PUBLIC_SENTRY_DSN = originalDsn;
    jest.resetModules();
  });

  it("is counted once the SDK is up, as the fact alone", async () => {
    process.env.EXPO_PUBLIC_SENTRY_DSN = "https://key@sentry.example.com/1";
    jest.resetModules();
    const mod = jest.requireActual<typeof import("@/lib/sentry")>("@/lib/sentry");
    // At launch, before the deferred init: it waits in the queue.
    mod.reportCorruptSessionCleared();
    await mod.initMobileSentry();

    const sdk = jest.requireMock<{ captureMessage: jest.Mock; captureException: jest.Mock }>(
      "@sentry/react-native",
    );
    expect(sdk.captureMessage).toHaveBeenCalledTimes(1);
    // A fixed text and one tag: no record, token, account or error text to carry.
    expect(sdk.captureMessage).toHaveBeenCalledWith(
      "Stored sign-in was not a session; cleared at launch",
      { level: "warning", tags: { area: "stored_session" } },
    );
    expect(sdk.captureException).not.toHaveBeenCalled();
  });
});
