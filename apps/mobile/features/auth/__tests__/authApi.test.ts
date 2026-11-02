import { loginWithApple, loginWithDev, loginWithGoogle } from "@/features/auth/api";
import { AccountExistsError, accountExistsProvider } from "@/features/auth/model/accountExists";
import { SignInRefusedError, signInRefusalKey } from "@/features/auth/model/signInRefusal";
import { ApiRequestError, fetchWithTimeout } from "@/lib/api/client";

jest.mock("@/lib/config", () => ({ getApiUrl: () => "https://api.test" }));
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => 0,
  requireTokenSession: jest.fn(),
  SessionChangedError: class extends Error {},
  getRefreshToken: jest.fn(),
  setTokenPair: jest.fn(),
}));
jest.mock("@/lib/api/client", () => ({
  ...jest.requireActual("@/lib/api/client"),
  apiUrl: (path: string) => `https://api.test${path}`,
  fetchWithTimeout: jest.fn(),
}));
jest.mock("@/lib/deviceSession", () => ({ deviceSessionFields: () => ({}) }));

const ACCOUNT_EXISTS = JSON.stringify({
  detail: {
    code: "account_exists",
    sign_in_with: "apple",
    message: "This email already has a Recall account.",
  },
});

function reply(status: number, body: string): Response {
  return { ok: status < 400, status, text: async () => body } as unknown as Response;
}

describe("accountExistsProvider", () => {
  it.each([
    [409, ACCOUNT_EXISTS, "apple"],
    [409, ACCOUNT_EXISTS.replace('"apple"', '"google"'), "google"],
    [409, ACCOUNT_EXISTS.replace('"apple"', '"dev"'), null],
    [409, JSON.stringify({ detail: "This email is taken" }), null],
    [409, JSON.stringify({ detail: { code: "other", sign_in_with: "apple" } }), null],
    [409, "not json", null],
    [401, ACCOUNT_EXISTS, null],
  ])("status %s body %s → %s", (status, body, expected) => {
    expect(accountExistsProvider(new ApiRequestError(status, body))).toBe(expected);
  });
});

describe("login errors", () => {
  it.each([
    ["Google", () => loginWithGoogle("id-token")],
    ["Apple", () => loginWithApple("id-token", null, "nonce")],
  ])("%s sign-in turns the 409 into AccountExistsError", async (_name, login) => {
    jest.mocked(fetchWithTimeout).mockResolvedValueOnce(reply(409, ACCOUNT_EXISTS));
    const error = await login().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(AccountExistsError);
    expect((error as AccountExistsError).signInWith).toBe("apple");
  });

  const refusal = (status: number, code: string, message: string) =>
    reply(status, JSON.stringify({ detail: { code, message } }));

  it.each([
    ["Google", () => loginWithGoogle("id-token"), refusal(401, "google_token_invalid", "Invalid Google ID token"), "login.error_token_invalid"],
    ["Google", () => loginWithGoogle("id-token"), refusal(503, "google_unavailable", "Google sign-in is unavailable right now"), "login.error_unavailable"],
    ["Apple", () => loginWithApple("id-token", null, "nonce"), refusal(401, "apple_email_unverified", "Apple email address is not verified"), "login.error_apple_email_unverified"],
    ["Apple", () => loginWithApple("id-token", null, "nonce"), refusal(429, "sign_in_rate_limited", "Too many login attempts. Try again shortly."), "login.error_rate_limited"],
    ["dev", () => loginWithDev(), refusal(403, "dev_auth_disabled", "Dev auth disabled"), "login.error_dev_disabled"],
    ["dev", () => loginWithDev(), refusal(503, "sign_in_unavailable", "Sign-in is unavailable right now. Try again in a moment."), "login.error_unavailable"],
    // Dev login passes the request limiter: with Redis down it answers the API's own outage body.
    ["dev", () => loginWithDev(), refusal(503, "unavailable", "Service temporarily unavailable. Please retry shortly."), "login.error_unavailable"],
  ] as const)("%s sign-in names the refusal's line, not the server's English (%#)", async (_name, login, answer, key) => {
    // The login screen showed the server's English as it came, in every language.
    jest.mocked(fetchWithTimeout).mockResolvedValueOnce(answer);
    const error = await login().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(SignInRefusedError);
    expect((error as SignInRefusedError).key).toBe(key);
  });
});

describe("signInRefusalKey", () => {
  const refused = (status: number, detail: unknown) =>
    new ApiRequestError(status, JSON.stringify({ detail }));

  it.each([
    // A code this phone does not know yet: the one generic line, whatever the status.
    [503, { code: "sign_in_paused", message: "Paused" }, "login.error_generic"],
    [401, { code: "google_token_expired", message: "Expired" }, "login.error_generic"],
    // No code: something in front of the API (a gateway's 503, the request limiter's 429).
    [503, "Service temporarily unavailable. Please retry shortly.", "login.error_unavailable"],
    [429, "Too many requests. Please slow down.", "login.error_rate_limited"],
    [401, "Invalid Google ID token", "login.error_generic"],
    [404, "Not Found", "login.error_generic"],
    [422, [{ msg: "Field required" }], "login.error_generic"],
  ])("status %s %j → %s", (status, detail, key) => {
    expect(signInRefusalKey(refused(status, detail))).toBe(key);
  });

  it("reads a body that is not JSON by its status", () => {
    expect(signInRefusalKey(new ApiRequestError(503, "<html>Bad gateway</html>"))).toBe("login.error_unavailable");
    expect(signInRefusalKey(new ApiRequestError(500, "Internal Server Error"))).toBe("login.error_generic");
  });
});

describe("sign-in deadline (NET-17)", () => {
  afterEach(() => jest.useRealTimers());

  it("gives up when the reply's body never finishes", async () => {
    jest.useFakeTimers();
    jest.mocked(fetchWithTimeout).mockResolvedValueOnce(
      { ok: true, status: 200, json: () => new Promise(() => undefined) } as unknown as Response,
    );
    const outcome = loginWithGoogle("id-token").catch((caught: unknown) => caught);
    await jest.advanceTimersByTimeAsync(15_000);
    await expect(outcome).resolves.toEqual(new SignInRefusedError("login.error_unreachable"));
  });
});

describe("a sign-in that gets no answer", () => {
  it.each([
    ["Google", () => loginWithGoogle("id-token")],
    ["Apple", () => loginWithApple("id-token", null, "nonce")],
    ["dev", () => loginWithDev()],
  ])("%s names the unreachable line, not the English", async (_name, login) => {
    // "Could not reach the Recall server…" or "Network request failed" was shown as it came.
    for (const failure of [new TypeError("Network request failed"), new Error("Could not reach the Recall server.")]) {
      jest.mocked(fetchWithTimeout).mockRejectedValueOnce(failure);
      const error = await login().catch((caught: unknown) => caught);
      expect(error).toEqual(new SignInRefusedError("login.error_unreachable"));
    }
  });
});

describe("the agreement a sign-in carries", () => {
  // The sign-in page's line says continuing agrees; the server records it with the sign-in,
  // so a new account no longer stops on a separate consent screen.
  it.each([
    ["/auth/google", () => loginWithGoogle("id-token")],
    ["/auth/apple", () => loginWithApple("id-token", null, "nonce")],
    ["/auth/dev", () => loginWithDev()],
  ])("%s says the user agreed by tapping", async (path, login) => {
    jest.mocked(fetchWithTimeout).mockResolvedValueOnce(
      { ok: true, status: 200, json: async () => ({}) } as unknown as Response,
    );
    await login();
    const [url, init] = jest.mocked(fetchWithTimeout).mock.calls.at(-1) ?? [];
    expect(url).toBe(`https://api.test${path}`);
    expect(JSON.parse(String(init?.body))).toMatchObject({ ai_data_consent: true });
  });
});
