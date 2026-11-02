import { speechApi } from "@/features/speech/api";
import { liveTalkErrorGate } from "@/features/speech/model/liveTalkLogic";
import { exchangeRealtimeSdp } from "@/features/speech/model/realtimeSdp";

jest.mock("@/features/speech/api", () => ({ speechApi: { connectRealtimeSession: jest.fn() } }));

const connect = speechApi.connectRealtimeSession as jest.Mock;

describe("exchangeRealtimeSdp", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.clearAllMocks();
  });

  it("sends the offer to Recall for the minted session and returns OpenAI's answer", async () => {
    // The phone holds no OpenAI secret: it never calls OpenAI over HTTP itself.
    const fetchMock = jest.fn();
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    connect.mockResolvedValueOnce({ sdp: "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111" });

    const localSdp = "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=sendrecv";
    await expect(exchangeRealtimeSdp("tok", "session-1", localSdp)).resolves.toBe(
      "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111",
    );

    expect(connect).toHaveBeenCalledWith("tok", { callId: "session-1", sdp: localSdp }, 15_000);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses an answer that is not SDP", async () => {
    connect.mockResolvedValueOnce({ sdp: "<html>" });

    await expect(exchangeRealtimeSdp("tok", "session-1", "v=0")).rejects.toThrow(
      "OpenAI Realtime returned an invalid SDP answer",
    );
  });

  // The server's codes: OpenAI opened no call (502 upstream_failed), the session is over.
  it.each([
    [{ status: 502, code: "upstream_failed" }, "connect_failed"],
    [{ status: 403, code: "live_talk_session_ended" }, "session_ended"],
  ])("keeps the server's refusal %j for the live talk gate", async (refusal, gate) => {
    connect.mockRejectedValueOnce(Object.assign(new Error("refused"), refusal));

    const error = await exchangeRealtimeSdp("tok", "session-1", "v=0").catch((caught: unknown) => caught);

    expect(liveTalkErrorGate(error)).toBe(gate);
  });
});
