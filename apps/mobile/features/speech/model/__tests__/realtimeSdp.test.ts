import { liveTalkErrorGate } from "@/features/speech/model/liveTalkLogic";
import { exchangeRealtimeSdp } from "@/features/speech/model/realtimeSdp";

describe("exchangeRealtimeSdp", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  it("posts raw local SDP with the ephemeral client secret and returns response text", async () => {
    const text = jest.fn(async () => "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111");
    const fetchMock = jest.fn(async () => ({ ok: true, status: 200, text }));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const localSdp = "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=sendrecv";
    await expect(exchangeRealtimeSdp("ek_test_short_lived", localSdp)).resolves.toBe(
      "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111",
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = (fetchMock.mock.calls[0] ?? []) as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("https://api.openai.com/v1/realtime/calls");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toEqual({
      Authorization: "Bearer ek_test_short_lived",
      "Content-Type": "application/sdp",
    });
    expect(init?.body).toBe(localSdp);
    expect(init?.signal).toBeInstanceOf(AbortSignal);
    expect(text).toHaveBeenCalledTimes(1);
  });

  it("includes the provider response text and status on non-ok failure", async () => {
    const text = jest.fn(async () => "ephemeral credential expired");
    const fetchMock = jest.fn(async () => ({ ok: false, status: 401, text }));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const error = await exchangeRealtimeSdp("ek_expired", "v=0").catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe(
      "OpenAI Realtime SDP exchange failed (401): ephemeral credential expired",
    );
    expect((error as Error & { status?: number }).status).toBe(401);
    expect(text).toHaveBeenCalledTimes(1);
  });

  // The provider's status is not Recall's: its 429 said this month's minutes were used,
  // its 403 opened the paywall, its 503 said Recall was down and the rest "update the app".
  it.each([400, 401, 403, 429, 500, 503])("says the provider's %i is a failed connection", async (status) => {
    globalThis.fetch = jest.fn(async () => ({ ok: false, status, text: async () => "no" })) as unknown as typeof fetch;

    const error = await exchangeRealtimeSdp("ek_test", "v=0").catch((caught: unknown) => caught);

    expect(liveTalkErrorGate(error)).toBe("connect_failed");
  });
});
