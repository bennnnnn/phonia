import { LIVE_TALK_UPSTREAM_FAILED } from "@/features/speech/model/liveTalkLogic";

const OPENAI_REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls";
const SDP_EXCHANGE_TIMEOUT_MS = 10_000;

/**
 * The one intentional provider-network exception: WebRTC media must be
 * negotiated directly, using only the backend-issued short-lived client
 * secret. Never proxy the media path or expose a permanent provider key.
 */
export async function exchangeRealtimeSdp(
  ephemeralClientSecret: string,
  localSdp: string,
): Promise<string> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), SDP_EXCHANGE_TIMEOUT_MS);
  try {
    const response = await fetch(OPENAI_REALTIME_CALLS_URL, {
      method: "POST",
      body: localSdp,
      headers: {
        Authorization: `Bearer ${ephemeralClientSecret}`,
        "Content-Type": "application/sdp",
      },
      signal: controller.signal,
    });
    const answerSdp = await response.text();
    if (!response.ok) {
      const error = new Error(
        `OpenAI Realtime SDP exchange failed (${response.status}): ${answerSdp.slice(0, 240)}`,
      ) as Error & { status?: number; code?: string };
      error.status = response.status;
      // The provider's status, not Recall's: its 429 is not this month's minutes, its 403 no paywall.
      error.code = LIVE_TALK_UPSTREAM_FAILED;
      throw error;
    }
    if (!answerSdp.includes("v=0")) {
      throw new Error("OpenAI Realtime returned an invalid SDP answer");
    }
    return answerSdp;
  } finally {
    clearTimeout(timeout);
  }
}
