/**
 * The metadata-only reports (outside review, 2026-11-01): a handled failure of a user's
 * action, a fence the phone refused, a fence that crashed. Each carries ids, codes and
 * counts, never message text or a fence's body, and none can flood Sentry.
 */
jest.mock("@sentry/react-native", () => ({
  init: jest.fn(),
  captureException: jest.fn(),
  captureMessage: jest.fn(),
  addBreadcrumb: jest.fn(),
}));

jest.mock("@/lib/config", () => ({ getApiUrl: () => "https://api.recall.test" }));

type SdkMock = { captureException: jest.Mock; captureMessage: jest.Mock };

const PRIVATE = "my private question";

const originalDsn = process.env.EXPO_PUBLIC_SENTRY_DSN;

/** lib/sentry.ts with fresh rate limits, and the SDK it reports to. */
async function freshSentry(started = true) {
  jest.resetModules();
  (globalThis as unknown as { __DEV__: boolean }).__DEV__ = false;
  process.env.EXPO_PUBLIC_SENTRY_DSN = "https://key@sentry.example.com/1";
  const mod = jest.requireActual<typeof import("@/lib/sentry")>("@/lib/sentry");
  if (started) await mod.initMobileSentry();
  const sdk = () => jest.requireMock<SdkMock>("@sentry/react-native");
  return { mod, sdk };
}

/** A refusal from our API, as `lib/api/errorBody.ts` builds one. */
function refusal(status: number, code: string | null, message = PRIVATE) {
  const { ApiRequestError } = jest.requireActual<typeof import("@/lib/api/errorBody")>("@/lib/api/errorBody");
  const body = JSON.stringify({ detail: code ? { code, message } : message });
  return new ApiRequestError(status, body, null, "m1abc-0123456789abcdef");
}

afterEach(() => {
  process.env.EXPO_PUBLIC_SENTRY_DSN = originalDsn;
  jest.useRealTimers();
});

describe("a handled failure", () => {
  it("names its area, class, status, code and call id, never the error's text", async () => {
    const { mod, sdk } = await freshSentry();
    mod.reportFailure("chat_load", refusal(500, "internal_error"));

    expect(sdk().captureException).toHaveBeenCalledTimes(1);
    const [reported, context] = sdk().captureException.mock.calls[0];
    expect(reported).toBeInstanceOf(Error);
    expect(reported.name).toBe("ApiRequestError");
    expect(reported.message).toBe("chat_load failed");
    expect(context).toEqual({
      level: "warning",
      tags: {
        area: "chat_load",
        error: "ApiRequestError",
        status: "500",
        code: "internal_error",
        request_id: "m1abc-0123456789abcdef",
      },
      fingerprint: ["handled_failure", "chat_load", "ApiRequestError", "500", "internal_error"],
    });
    expect(JSON.stringify(sdk().captureException.mock.calls)).not.toContain(PRIVATE);
    expect(String(reported.stack)).not.toContain(PRIVATE);
  });

  it("drops a message over several lines, even a line that reads like a frame", async () => {
    const { mod, sdk } = await freshSentry();
    const error = new Error("could not read body:\n  at noon call Sam");
    error.stack = `Error: ${error.message}\n    at readBody (index.bundle:5:6)`;
    mod.reportFailure("chat_load", error);

    const [reported] = sdk().captureException.mock.calls[0];
    expect(reported.stack).toBe("Error: chat_load failed\n    at readBody (index.bundle:5:6)");
  });

  it("keeps the stack's frames and drops the message line", async () => {
    const { mod, sdk } = await freshSentry();
    const error = new TypeError(`cannot read ${PRIVATE}`);
    error.stack = `TypeError: cannot read ${PRIVATE}\n    at loadPage (index.bundle:1:2)\n    at run (index.bundle:3:4)`;
    mod.reportFailure("chat_page", error);

    const [reported, context] = sdk().captureException.mock.calls[0];
    expect(reported.stack).toBe(
      "TypeError: chat_page failed\n    at loadPage (index.bundle:1:2)\n    at run (index.bundle:3:4)",
    );
    expect(context.tags).toEqual({ area: "chat_page", error: "TypeError" });
  });

  it("takes a store's code or an attachment's reason, and no sentence", async () => {
    const { mod, sdk } = await freshSentry();
    mod.reportFailure("purchase", Object.assign(new Error(PRIVATE), { code: "PRODUCT_NOT_AVAILABLE" }));
    mod.reportFailure("attachment_upload", Object.assign(new Error(PRIVATE), { name: "AttachmentError", reason: "upload_failed" }));
    mod.reportFailure("purchase_sync", Object.assign(new Error("x"), { code: PRIVATE, status: 1.5 }));
    mod.reportFailure("paywall_load", "a thrown string");

    const tags = sdk().captureException.mock.calls.map(([, context]) => context.tags);
    expect(tags).toEqual([
      { area: "purchase", error: "Error", code: "PRODUCT_NOT_AVAILABLE" },
      { area: "attachment_upload", error: "AttachmentError", code: "upload_failed" },
      { area: "purchase_sync", error: "Error" },
      { area: "paywall_load", error: "unknown" },
    ]);
  });

  it("is not reported when no API answered, the call was cancelled, or the sign-in changed", async () => {
    const { mod, sdk } = await freshSentry();
    const { serverUnreachableError, abortError } = jest.requireActual<typeof import("@/lib/api/deadline")>(
      "@/lib/api/deadline",
    );
    mod.reportFailure("chat_load", serverUnreachableError());
    mod.reportFailure("chat_load", new TypeError("Network request failed"));
    mod.reportFailure("chat_load", abortError());
    mod.reportFailure("chat_load", Object.assign(new Error("changed"), { name: "SessionChangedError" }));
    expect(sdk().captureException).not.toHaveBeenCalled();
  });

  it("reports one of a kind every ten minutes and twenty an hour", async () => {
    jest.useFakeTimers({ now: new Date("2026-11-01T10:00:00Z") });
    const { mod, sdk } = await freshSentry();
    const failing = () => refusal(503, "unavailable_x");
    for (let i = 0; i < 5; i += 1) mod.reportFailure("chat_refresh", failing());
    expect(sdk().captureException).toHaveBeenCalledTimes(1);

    jest.setSystemTime(new Date("2026-11-01T10:10:00Z"));
    mod.reportFailure("chat_refresh", failing());
    expect(sdk().captureException).toHaveBeenCalledTimes(2);

    // Each status a separate kind: the hour's budget still caps them.
    for (let status = 400; status < 440; status += 1) mod.reportFailure("chat_page", refusal(status, null));
    expect(sdk().captureException).toHaveBeenCalledTimes(20);

    jest.setSystemTime(new Date("2026-11-01T11:10:01Z"));
    mod.reportFailure("chat_page", refusal(450, null));
    expect(sdk().captureException).toHaveBeenCalledTimes(21);
  });
});

describe("a refused fence", () => {
  it("is one event naming the fence and the reason", async () => {
    const { mod, sdk } = await freshSentry();
    mod.reportFenceRefused("simulation", "unknown_kind");
    expect(sdk().captureMessage).toHaveBeenCalledWith("Fence refused", {
      level: "warning",
      tags: { area: "fence_refused", fence: "simulation", reason: "unknown_kind" },
      fingerprint: ["fence_refused", "simulation", "unknown_kind"],
    });
  });

  it("reports each fence and reason once an hour, and ten an hour in all", async () => {
    jest.useFakeTimers({ now: new Date("2026-11-01T10:00:00Z") });
    const { mod, sdk } = await freshSentry();
    // A long chat of the same broken graph.
    for (let i = 0; i < 50; i += 1) mod.reportFenceRefused("graph", "invalid_json");
    expect(sdk().captureMessage).toHaveBeenCalledTimes(1);

    const fences = ["geometry", "quiz", "array", "clarify", "chart", "mermaid", "calculator", "chem_scene", "molecule", "places", "steps"] as const;
    for (const fence of fences) mod.reportFenceRefused(fence, "invalid_spec");
    expect(sdk().captureMessage).toHaveBeenCalledTimes(10);

    jest.setSystemTime(new Date("2026-11-01T11:00:01Z"));
    mod.reportFenceRefused("graph", "invalid_json");
    expect(sdk().captureMessage).toHaveBeenCalledTimes(11);
  });

  it("waits before the SDK is up in half the early queue, leaving room for a crash", async () => {
    const { mod, sdk } = await freshSentry(false);
    const fences = ["geometry", "graph", "quiz", "array", "clarify", "chart", "mermaid"] as const;
    for (const fence of fences) mod.reportFenceRefused(fence, "invalid_spec");
    for (let i = 0; i < 8; i += 1) mod.reportBoundaryError("message_row", new Error(`crash ${i}`));
    await mod.initMobileSentry();

    expect(sdk().captureMessage).toHaveBeenCalledTimes(5);
    expect(sdk().captureException).toHaveBeenCalledTimes(5);
  });
});

describe("a fence that crashed", () => {
  it("is tagged with the fence and sent without its message", async () => {
    const { mod, sdk } = await freshSentry();
    const error = new SyntaxError(`Unexpected token in ${PRIVATE}`);
    error.stack = `SyntaxError: Unexpected token in ${PRIVATE}\n    at parseGraph (index.bundle:9:9)`;
    mod.reportFenceCrash("graph", error, "\n    in FunctionGraphBlock");

    const [reported, context] = sdk().captureException.mock.calls[0];
    expect(reported.name).toBe("SyntaxError");
    expect(reported.message).toBe("Fence render failed");
    expect(reported.stack).toBe("SyntaxError: Fence render failed\n    at parseGraph (index.bundle:9:9)");
    expect(context).toEqual({
      tags: { boundary: "fence", fence: "graph" },
      contexts: { react: { componentStack: "\n    in FunctionGraphBlock" } },
    });
    expect(JSON.stringify(sdk().captureException.mock.calls)).not.toContain(PRIVATE);
  });

  it("reports the same crash once a minute however many blocks hit it", async () => {
    jest.useFakeTimers({ now: new Date("2026-11-01T10:00:00Z") });
    const { mod, sdk } = await freshSentry();
    for (let i = 0; i < 30; i += 1) mod.reportFenceCrash("quiz", new TypeError("x"));
    mod.reportFenceCrash("chart", new TypeError("x"));
    expect(sdk().captureException).toHaveBeenCalledTimes(2);
  });
});
