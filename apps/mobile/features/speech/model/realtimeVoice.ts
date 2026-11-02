import { Platform } from "react-native";

import { speechApi } from "@/features/speech/api";
import { createRealtimeMicGate } from "@/features/speech/model/realtimeMicGate";
import {
  createRealtimePeer,
  debugRealtime,
  loadWebRtc,
  openRealtimeMicrophone,
} from "@/features/speech/model/realtimePeer";
import { runRealtimeFunctionCall } from "@/features/speech/model/realtimeTools";
import {
  initialRealtimeTurnState,
  reduceRealtimeTurn,
  type RealtimeTurnCommand,
  type RealtimeTurnEvent,
  type RealtimeVoiceEvent,
} from "@/features/speech/model/realtimeTurnState";
import { isPhysicalDevice } from "@/lib/expoRuntime";

export type { RealtimeVoiceEvent };

export type RealtimeVoiceSession = {
  callId: string | null;
  /** Seconds the server reserved from this month's minutes; hang up by then. */
  maxDurationSeconds: number | null;
  setMuted: (muted: boolean) => void;
  cancelResponse: () => void;
  close: () => void;
};

const TOOL_LIMIT_RESULT = {
  content: "Voice lookup limit reached. Answer from available context and disclose missing facts.",
};

export function isRealtimeVoiceAvailable(): boolean {
  return loadWebRtc() !== null;
}

/**
 * VoiceProcessing IO can deadlock CoreAudio on the iOS Simulator when
 * expo-audio has also touched the session. Only the Simulator uses the
 * half-duplex workaround; physical iOS/Android devices need AEC for barge-in.
 * If ExpoDevice is not in this binary, use the Simulator path so Live Talk
 * can start until the next native rebuild.
 */
export function webRtcMicConstraints(): {
  echoCancellation: boolean;
  noiseSuppression: boolean;
  autoGainControl: boolean;
} {
  if (Platform.OS === "ios" && isPhysicalDevice() !== true) {
    return { echoCancellation: false, noiseSuppression: false, autoGainControl: false };
  }
  return { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
}

/** Each lookup answers the model; a full set from the current turn asks it to go on. */
function runToolCalls(
  { epoch, turnId, calls }: Extract<RealtimeTurnCommand, { type: "run_tools" }>,
  context: { token: string; chatId?: string | null; callId: string | null },
  dispatch: (event: RealtimeTurnEvent) => void,
): void {
  const { token, chatId, callId } = context;
  void Promise.all(calls.map(async ({ call, withinLimit }) => {
    const result = withinLimit && callId && chatId
      ? await runRealtimeFunctionCall(call, { token, chatId, callId, turnId })
      : TOOL_LIMIT_RESULT;
    dispatch({ type: "tool_output", epoch, callId: call.call_id, result });
  })).then(() => dispatch({ type: "tools_settled", epoch }));
}

/**
 * The server reserved this month's minutes when it minted the call; a call
 * that never connected gives them back (it is charged only the seconds since
 * the mint). The mint may still be in flight when the offer fails, so wait for
 * it: a call id that arrives after the failure is ended too.
 */
function releaseMintedSession(
  token: string,
  credential: ReturnType<typeof speechApi.createRealtimeSession>,
): void {
  void credential
    .then(({ call_id: callId }) => (callId ? speechApi.endRealtimeSession(token, callId) : undefined))
    .catch(() => {});
}

export async function createRealtimeVoiceSession(options: {
  token: string;
  chatId?: string | null;
  onEvent: (event: RealtimeVoiceEvent) => void;
}): Promise<RealtimeVoiceSession> {
  const webrtc = loadWebRtc();
  if (!webrtc) {
    throw new Error("webrtc_unavailable");
  }
  const mic = webRtcMicConstraints();
  const { stream, audioTracks } = await openRealtimeMicrophone(webrtc, mic);

  let callId: string | null = null;
  let maxDurationSeconds: number | null = null;
  let turn = initialRealtimeTurnState(mic.echoCancellation);

  const perform = (command: RealtimeTurnCommand) => {
    switch (command.type) {
      case "send":
        return peer.send(command.payload);
      case "emit":
        return options.onEvent(command.event);
      case "set_mic":
        return gate.setMic(command.enabled);
      case "start_timer":
        return gate.start(command.timer, command.ms, command.then);
      case "clear_timer":
        return gate.clear(command.timer);
      case "run_tools":
        return runToolCalls(command, { token: options.token, chatId: options.chatId, callId }, dispatch);
      case "log":
        return debugRealtime(command.stage, command.detail);
    }
  };
  const dispatch = (event: RealtimeTurnEvent) => {
    const step = reduceRealtimeTurn(turn, event);
    turn = step.state;
    for (const command of step.commands) perform(command);
  };

  const gate = createRealtimeMicGate(audioTracks, dispatch);
  const peer = createRealtimePeer(webrtc, stream, {
    onOpen: () => dispatch({ type: "channel_open" }),
    onMessage: (event) => dispatch({ type: "server_event", event, receivedAt: Date.now() }),
    onPeerFailed: (message) => dispatch({ type: "peer_failed", message }),
    onChannelFailed: (message) => dispatch({ type: "channel_failed", message }),
  });
  const tearDown = () => {
    gate.clearAll();
    peer.close();
  };

  // Mint the short-lived credential while local ICE gathering proceeds. The
  // permanent OpenAI API key stays on Recall's server; only this ek_ token is
  // ever exposed to the app. Every failure from here releases the mint.
  const credentialPromise = speechApi.createRealtimeSession(options.token, {
    chatId: options.chatId,
    bargeIn: mic.echoCancellation,
  });

  try {
    const offerSdp = await peer.createOffer();
    const credential = await credentialPromise;
    callId = credential.call_id;
    maxDurationSeconds = credential.max_duration_seconds ?? null;
    debugRealtime("client-secret-ready", {
      model: credential.model,
      expiresAt: credential.expires_at,
    });
    await peer.connect(credential.client_secret, offerSdp);
  } catch (error) {
    dispatch({ type: "close" });
    tearDown();
    peer.closeChannel();
    releaseMintedSession(options.token, credentialPromise);
    throw error;
  }

  return {
    callId,
    maxDurationSeconds,
    setMuted: (muted: boolean) => dispatch({ type: "set_muted", muted }),
    cancelResponse: () => dispatch({ type: "cancel_response" }),
    close: () => {
      if (turn.closed) return;
      dispatch({ type: "close" });
      debugRealtime("closing-session");
      peer.closeChannel();
      tearDown();
    },
  };
}
