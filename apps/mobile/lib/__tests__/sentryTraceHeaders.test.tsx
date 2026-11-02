/**
 * Sentry's trace headers (`sentry-trace`, `baggage`: the DSN's public key, the
 * environment, a trace id) go on requests to our API only. The real SDK, started by
 * initMobileSentry, instruments fetch; the requests below are the phone's own kinds.
 */
jest.mock("expo/src/winter", () => ({}));
jest.mock("@/lib/config", () => ({ getApiUrl: () => "https://api.recall.test" }));

class MockExpoEmitter {
  addListener() { return { remove: () => {} }; }
  removeListener() {}
  removeAllListeners() {}
  emit() {}
  listenerCount() { return 0; }
}
(globalThis as unknown as { expo: unknown }).expo = {
  EventEmitter: MockExpoEmitter,
  NativeModule: MockExpoEmitter,
  SharedObject: MockExpoEmitter,
  SharedRef: MockExpoEmitter,
  modules: {},
  uuidv4: () => "uuid",
  uuidv5: () => "uuid",
  getViewConfig: () => null,
};

const sent: { url: string; traced: boolean }[] = [];
/** The phone's fetch is Expo's native one (`expo/fetch`), which the SDK traces. */
const phoneFetch = Object.assign(
  jest.fn(async (url: string, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    sent.push({ url, traced: headers.has("sentry-trace") || headers.has("baggage") });
    return new Response("{}");
  }),
  { [Symbol.for("expo.builtin")]: true },
);

// The real SDK is imported in the test: with a cold jest cache (CI) compiling it takes
// longer than the default 5 s, and the test failed on its timeout, not its assertion.
it("puts trace headers on our API's requests and on no one else's", async () => {
  process.env.EXPO_PUBLIC_SENTRY_DSN = "https://key@o1.ingest.sentry.io/1";
  (globalThis as unknown as { __DEV__: boolean }).__DEV__ = false;
  const { initMobileSentry } = await import("@/lib/sentry");
  await import("@sentry/react-native");
  Object.defineProperty(globalThis, "fetch", { value: phoneFetch, writable: true, configurable: true });
  await initMobileSentry();
  for (const url of [
    "https://api.recall.test/chats",
    "https://api.recall.test/chats/1/messages?limit=40",
    "https://api.openai.com/v1/realtime/calls",
    "https://clients3.google.com/generate_204",
    "https://bucket.r2.cloudflarestorage.com/upload?X-Amz-Signature=x",
    "https://api.recall.test.evil.example/x",
  ]) {
    await globalThis.fetch(url);
  }
  expect(sent.filter((request) => request.traced).map((request) => request.url)).toEqual([
    "https://api.recall.test/chats",
    "https://api.recall.test/chats/1/messages?limit=40",
  ]);
}, 60_000);
