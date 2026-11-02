import { request } from "@/lib/api/client";
import { readErrorBody } from "@/lib/api/errorBody";
import { CONSENT_REQUIRED_CODE, setConsentRequiredHandler } from "@/lib/api/consentRefusal";

jest.mock("@/lib/config", () => ({ getApiUrl: () => "http://test.local" }));

let mockSessionGeneration = 0;

jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => mockSessionGeneration,
  requireTokenSession: jest.fn(),
  SessionChangedError: class extends Error {},
  getRefreshToken: jest.fn(),
  setTokenPair: jest.fn(),
}));

const mockFetch = jest.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

const CONSENT_BODY = JSON.stringify({
  detail: { code: "consent_required", message: "Agree to how Recall uses outside AI services." },
});
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("a consent_required refusal", () => {
  const opened = jest.fn();

  beforeEach(() => {
    mockFetch.mockReset();
    opened.mockReset();
    mockSessionGeneration = 0;
    setConsentRequiredHandler(opened);
  });

  afterEach(() => setConsentRequiredHandler(null));

  it("opens the consent screen, and the caller still gets its error", async () => {
    mockFetch.mockResolvedValueOnce(new Response(CONSENT_BODY, { status: 403 }));
    await expect(request("/speech/transcribe", "tok")).rejects.toMatchObject({
      status: 403,
      code: "consent_required",
      message: "Agree to how Recall uses outside AI services.",
    });
    await flush();
    expect(opened).toHaveBeenCalledTimes(1);
  });

  it("leaves an ordinary 403 alone", async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Voice is a Pro feature." }), { status: 403 }),
    );
    await expect(request("/speech/tts", "tok")).rejects.toMatchObject({ status: 403 });
    await flush();
    expect(opened).not.toHaveBeenCalled();
  });

  it.each([
    [CONSENT_BODY, true],
    ['{"detail": "consent_required"}', false],
    ['{"detail": {"code": "quota_exceeded"}}', false],
    ["not json", false],
    ["null", false],
  ])("reads %s as a consent refusal: %s", (body, expected) => {
    expect(readErrorBody(body).code === CONSENT_REQUIRED_CODE).toBe(expected);
  });
});
