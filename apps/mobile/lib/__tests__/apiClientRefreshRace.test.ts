/**
 * Two refreshes of one refresh token at once must not sign the phone out.
 *
 * The server rotates the token on each refresh and, past a few seconds, takes a rotated-out
 * token for a stolen one: it revokes every session of the account and answers 401, and the
 * phone signs out. 2026-11-02: two refreshes reached the server together, a third came with a
 * token one of them had rotated, and the app signed itself out. The phone sends one refresh
 * per token: every caller, in every copy of the client module, joins it. Only a refused
 * token signs out; an outage, a 5xx or a timeout never does.
 */
import { accessTokenNeedsRefresh } from "@/lib/api/client";

jest.mock("@/lib/config", () => ({ getApiUrl: () => "http://test.local" }));

/** The phone's secure store, one for every copy of the client (as on a device). */
const mockStore = { refreshToken: "r0" as string | null };
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => 1,
  requireTokenSession: () => {},
  SessionChangedError: class extends Error {},
  getRefreshToken: async () => mockStore.refreshToken,
  setTokenPair: async (_access: string, refresh: string) => {
    mockStore.refreshToken = refresh;
    return true;
  },
}));

type Client = typeof import("@/lib/api/client");

const jwt = (expSeconds: number, n: number) => `h.${btoa(JSON.stringify({ exp: expSeconds, n }))}.s`;
const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

type Server = {
  refreshes: string[];
  /** Live refresh tokens; a rotated-out one presented again revokes them all. */
  live: Set<string>;
  access: Set<string>;
  /** What /auth/refresh answers instead of rotating, when set. */
  failWith: (() => Response | Promise<Response>) | null;
};

/** The server as it was: rotation with strict reuse detection, no grace. */
function serve(): Server {
  const server: Server = { refreshes: [], live: new Set(["r0"]), access: new Set(), failWith: null };
  const rotated = new Set<string>();
  globalThis.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    if (String(url).endsWith("/auth/refresh")) {
      const presented = (JSON.parse(String(init?.body)) as { refresh_token: string }).refresh_token;
      server.refreshes.push(presented);
      await wait(30);
      if (server.failWith) return server.failWith();
      if (!server.live.has(presented)) {
        if (rotated.has(presented)) {
          server.live.clear();
          server.access.clear();
        }
        return new Response("", { status: 401 });
      }
      server.live.delete(presented);
      rotated.add(presented);
      const refresh = `r${server.refreshes.length}`;
      const access = jwt(Date.now() / 1000 + 3600, server.refreshes.length);
      server.live.add(refresh);
      server.access.add(access);
      return new Response(JSON.stringify({ access_token: access, refresh_token: refresh }));
    }
    const token = (init?.headers as Record<string, string>).Authorization?.slice("Bearer ".length) ?? "";
    await wait(5);
    return new Response(server.access.has(token) ? "{}" : "", { status: server.access.has(token) ? 200 : 401 });
  }) as typeof fetch;
  return server;
}

/** A fresh copy of the client module, as Fast Refresh or a second bundle would load it. */
function loadClient(signOuts: string[], name: string): Client {
  let client: Client | undefined;
  jest.isolateModules(() => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- a second module instance on purpose
    client = require("@/lib/api/client") as Client;
  });
  if (!client) throw new Error("client did not load");
  client.setUnauthorizedHandler(() => signOuts.push(name));
  return client;
}

const expired = () => jwt(Date.now() / 1000 - 10, 0);

beforeEach(() => {
  mockStore.refreshToken = "r0";
});

it("reads an expired token as one to refresh", () => {
  expect(accessTokenNeedsRefresh(expired())).toBe(true);
});

it("sends one refresh for many callers of one client, and stays signed in", async () => {
  const server = serve();
  const signOuts: string[] = [];
  const client = loadClient(signOuts, "app");
  const results = await Promise.allSettled(["/a", "/b", "/c"].map((path) => client.request(path, expired())));
  expect(results.map((result) => result.status)).toEqual(["fulfilled", "fulfilled", "fulfilled"]);
  expect(server.refreshes).toEqual(["r0"]);
  expect(signOuts).toEqual([]);
  expect(server.live).toEqual(new Set([mockStore.refreshToken]));
});

it("sends one refresh for two copies of the client module, and stays signed in", async () => {
  const server = serve();
  const signOuts: string[] = [];
  const first = loadClient(signOuts, "first");
  const second = loadClient(signOuts, "second");
  expect(second).not.toBe(first);
  const results = await Promise.allSettled([
    first.request("/todos", expired()),
    second.request("/chats", expired()),
  ]);
  expect(results.map((result) => result.status)).toEqual(["fulfilled", "fulfilled"]);
  expect(server.refreshes).toEqual(["r0"]);
  expect(signOuts).toEqual([]);
  // One valid session: the pair the phone stored is the one the server holds.
  expect(server.live).toEqual(new Set([mockStore.refreshToken]));
  // The next refresh starts a new flight, with the rotated token.
  mockStore.refreshToken = [...server.live][0];
  await first.request("/me", expired());
  expect(server.refreshes).toEqual(["r0", "r1"]);
  expect(signOuts).toEqual([]);
});

it.each([
  ["a 503", () => new Response(JSON.stringify({ detail: "Service unavailable" }), { status: 503 })],
  ["a 500", () => new Response("oops", { status: 500 })],
  ["no answer", () => Promise.reject(new TypeError("Network request failed"))],
  ["an unreadable answer", () => new Response("{}")],
])("keeps the phone signed in when the refresh meets %s", async (_name, answer) => {
  const server = serve();
  server.failWith = answer;
  const signOuts: string[] = [];
  const client = loadClient(signOuts, "app");
  const results = await Promise.allSettled([client.request("/a", expired()), client.request("/b", expired())]);
  expect(results.map((result) => result.status)).toEqual(["rejected", "rejected"]);
  expect(signOuts).toEqual([]);
  expect(mockStore.refreshToken).toBe("r0");
  // Once the server answers again, the same token refreshes.
  server.failWith = null;
  await expect(client.request("/c", expired())).resolves.toEqual({});
  expect(signOuts).toEqual([]);
});

it("signs out when the server refuses the refresh token itself", async () => {
  const server = serve();
  server.live.clear();
  const signOuts: string[] = [];
  const client = loadClient(signOuts, "app");
  await expect(client.request("/a", expired())).rejects.toMatchObject({ status: 401 });
  expect(server.refreshes).toEqual(["r0"]);
  expect(signOuts).toEqual(["app"]);
});
