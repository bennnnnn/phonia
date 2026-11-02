import { speechApi } from "@/features/speech/api";

const SDP_EXCHANGE_TIMEOUT_MS = 15_000;

/**
 * Trades the phone's WebRTC offer for OpenAI's answer through Recall's API
 * (`POST /speech/live/connect`). The server opens the call with the session's
 * short-lived secret, which never reaches the phone, so it knows the call and
 * hangs it up itself when the session ends or its minutes run out. Only the
 * media then flows directly between the phone and OpenAI.
 *
 * A refusal keeps the server's status and code: its `upstream_failed` (OpenAI
 * opened no call) reads as a failed connection, `live_talk_session_ended` as
 * the session being over.
 */
export async function exchangeRealtimeSdp(
  token: string,
  sessionId: string,
  localSdp: string,
): Promise<string> {
  const { sdp: answerSdp } = await speechApi.connectRealtimeSession(
    token,
    { callId: sessionId, sdp: localSdp },
    SDP_EXCHANGE_TIMEOUT_MS,
  );
  if (typeof answerSdp !== "string" || !answerSdp.includes("v=0")) {
    throw new Error("OpenAI Realtime returned an invalid SDP answer");
  }
  return answerSdp;
}
