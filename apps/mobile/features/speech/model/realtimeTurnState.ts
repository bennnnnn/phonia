import {
  LIVE_TALK_CONNECT_WARMUP_MS,
  LIVE_TALK_PLAYBACK_TAIL_MS,
  LIVE_TALK_SESSION_READY_FALLBACK_MS,
  isLikelyAssistantEcho,
  isLiveTalkSilenceHallucination,
  liveTalkLocalMicEnabled,
  liveTalkShouldCreateResponse,
  liveTalkTranscriptText,
} from "@/features/speech/model/liveTalkLogic";
import {
  realtimeFunctionCalls,
  type RealtimeFunctionCall,
  type RealtimeToolResult,
} from "@/features/speech/model/realtimeTools";
import type { SearchSource } from "@/lib/api/types";

export type RealtimeVoiceEvent =
  | { type: "connected" }
  | { type: "speech_started"; turnId?: string }
  | { type: "speech_stopped" }
  | { type: "response_started" }
  | { type: "user_transcript"; text: string }
  | { type: "assistant_transcript"; text: string; final: boolean }
  | { type: "response_done" }
  | { type: "response_interrupted" }
  | { type: "search_sources"; sources: SearchSource[] }
  /** ``fatal``: the connection itself is gone (peer or channel failed); the session must close. */
  | { type: "error"; message: string; fatal?: boolean };

/** session_ready ends the connect warmup; mic_resume ends playback. */
export type RealtimeTimer = "session_ready" | "mic_resume";

export type RealtimeTurnEvent =
  /** One parsed data-channel message; receivedAt names an utterance that has no item_id. */
  | { type: "server_event"; event: Record<string, unknown>; receivedAt: number }
  | { type: "channel_open" }
  | { type: "peer_failed"; message: string }
  | { type: "channel_failed"; message: string }
  | { type: "session_ready"; reason: string }
  | { type: "resume_mic" }
  | { type: "playback_fallback" }
  | { type: "tool_output"; epoch: number; callId: string; result: RealtimeToolResult }
  | { type: "tools_settled"; epoch: number }
  | { type: "set_muted"; muted: boolean }
  | { type: "cancel_response" }
  | { type: "close" };

export type RealtimeTurnCommand =
  | { type: "send"; payload: Record<string, unknown> }
  | { type: "emit"; event: RealtimeVoiceEvent }
  | { type: "set_mic"; enabled: boolean }
  /** Replaces a pending timer of the same name; `then` is dispatched when it fires. */
  | { type: "start_timer"; timer: RealtimeTimer; ms: number; then: RealtimeTurnEvent }
  | { type: "clear_timer"; timer: RealtimeTimer }
  | { type: "run_tools"; epoch: number; turnId: string; calls: { call: RealtimeFunctionCall; withinLimit: boolean }[] }
  | { type: "log"; stage: string; detail?: unknown };

export type RealtimeTurnState = {
  /** Echo cancellation is on, so the user may talk over the reply. */
  bargeIn: boolean;
  closed: boolean;
  userMuted: boolean;
  sessionReadyForTurns: boolean;
  assistantSpeaking: boolean;
  userSpeaking: boolean;
  suppressCurrentInputTurn: boolean;
  acceptedUserUtterance: boolean;
  responseFinished: boolean;
  sawOutputAudioStopped: boolean;
  activeInputId: string;
  activeResponseId: string | null;
  /** Bumped by each accepted utterance and by stop; a lookup from an older epoch is stale. */
  turnEpoch: number;
  toolCallsThisTurn: number;
  completedToolCalls: ReadonlySet<string>;
  assistantTranscript: string;
  lastAssistantText: string;
};

type RealtimeTurnStep = { state: RealtimeTurnState; commands: RealtimeTurnCommand[] };

const PLAYBACK_UNMUTE_FALLBACK_MS = 12_000;
const MAX_TOOL_CALLS_PER_RESPONSE = 8;
const MAX_LOOKUPS_PER_TURN = 2;

export function initialRealtimeTurnState(bargeIn: boolean): RealtimeTurnState {
  return {
    bargeIn,
    closed: false,
    userMuted: false,
    sessionReadyForTurns: false,
    assistantSpeaking: false,
    userSpeaking: false,
    suppressCurrentInputTurn: false,
    acceptedUserUtterance: false,
    responseFinished: false,
    sawOutputAudioStopped: false,
    activeInputId: "",
    activeResponseId: null,
    turnEpoch: 0,
    toolCallsThisTurn: 0,
    completedToolCalls: new Set(),
    assistantTranscript: "",
    lastAssistantText: "",
  };
}

function sessionTurnSnapshot(event: Record<string, unknown>): Record<string, unknown> {
  const session = event.session;
  if (!session || typeof session !== "object") return { hasSession: false };
  const root = session as Record<string, unknown>;
  const audio = root.audio;
  let turn: Record<string, unknown> | null = null;
  if (audio && typeof audio === "object") {
    const input = (audio as Record<string, unknown>).input;
    if (input && typeof input === "object") {
      const nested = (input as Record<string, unknown>).turn_detection;
      if (nested && typeof nested === "object") turn = nested as Record<string, unknown>;
    }
  }
  if (!turn && root.turn_detection && typeof root.turn_detection === "object") {
    turn = root.turn_detection as Record<string, unknown>;
  }
  return {
    hasSession: true,
    vad: typeof turn?.type === "string" ? turn.type : null,
    create_response: turn?.create_response ?? null,
    interrupt_response: turn?.interrupt_response ?? null,
  };
}

/** The handlers below update a copy of the state and append the commands it implies, in order. */
type Out = RealtimeTurnCommand[];
const send = (out: Out, payload: Record<string, unknown>) => { out.push({ type: "send", payload }); };
const emit = (out: Out, event: RealtimeVoiceEvent) => { out.push({ type: "emit", event }); };
const log = (out: Out, stage: string, detail?: unknown) => { out.push({ type: "log", stage, detail }); };
const startTimer = (out: Out, timer: RealtimeTimer, ms: number, then: RealtimeTurnEvent) => {
  out.push({ type: "start_timer", timer, ms, then });
};
const clearMicResume = (out: Out) => { out.push({ type: "clear_timer", timer: "mic_resume" }); };

function syncMic(s: RealtimeTurnState, out: Out): void {
  const enabled = liveTalkLocalMicEnabled(s.userMuted, s.assistantSpeaking, s.bargeIn);
  out.push({ type: "set_mic", enabled });
  log(out, "microphone-gate", { enabled, userMuted: s.userMuted, assistantSpeaking: s.assistantSpeaking });
}

function dropEchoInput(out: Out, reason: string, cancelResponse: boolean): void {
  send(out, { type: "input_audio_buffer.clear" });
  if (cancelResponse) send(out, { type: "response.cancel" });
  log(out, "dropped-echo-input", { reason, cancelResponse });
}

function emitError(s: RealtimeTurnState, out: Out, message: string, fatal = false): void {
  log(out, "realtime-error", message);
  if (!s.closed) emit(out, fatal ? { type: "error", message, fatal } : { type: "error", message });
}

function onSpeechStarted(s: RealtimeTurnState, out: Out, event: Record<string, unknown>, receivedAt: number): void {
  s.suppressCurrentInputTurn = (!s.bargeIn && s.assistantSpeaking) || s.userMuted || !s.sessionReadyForTurns;
  if (s.suppressCurrentInputTurn) {
    s.acceptedUserUtterance = false;
    dropEchoInput(out, "speech-before-user-turn", false);
    return;
  }
  if (s.bargeIn && s.assistantSpeaking) {
    // Server WebRTC VAD cancels and truncates unplayed audio automatically.
    emit(out, { type: "response_interrupted" });
    s.assistantSpeaking = false;
    s.assistantTranscript = "";
    s.activeResponseId = null;
    clearMicResume(out);
  }
  s.activeInputId = typeof event.item_id === "string" ? event.item_id : String(receivedAt);
  s.userSpeaking = true;
  s.turnEpoch += 1;
  s.toolCallsThisTurn = 0;
  s.acceptedUserUtterance = true;
  emit(out, { type: "speech_started", turnId: s.activeInputId });
}

function onSpeechStopped(s: RealtimeTurnState, out: Out): void {
  s.userSpeaking = false;
  if (s.suppressCurrentInputTurn) {
    s.suppressCurrentInputTurn = false;
    s.acceptedUserUtterance = false;
    return;
  }
  emit(out, { type: "speech_stopped" });
  if (!liveTalkShouldCreateResponse(s)) return;
  s.acceptedUserUtterance = false;
  s.assistantSpeaking = true;
  syncMic(s, out);
  send(out, { type: "response.create" });
  log(out, "response-create", "speech_stopped");
}

function onResponseCreated(s: RealtimeTurnState, out: Out, response: { id?: string } | undefined): void {
  if (s.bargeIn && s.userSpeaking) {
    // A response.create can cross the next speech_started in flight.
    // Cancel that old response without clearing the user's new audio.
    send(out, { type: "response.cancel", response_id: response?.id });
    return;
  }
  if (s.suppressCurrentInputTurn) {
    dropEchoInput(out, "response-before-user-turn", true);
    return;
  }
  s.activeResponseId = response?.id ?? null;
  s.responseFinished = false;
  s.assistantTranscript = "";
  clearMicResume(out);
  s.assistantSpeaking = true;
  s.acceptedUserUtterance = false;
  s.sawOutputAudioStopped = false;
  syncMic(s, out);
  if (!s.bargeIn) send(out, { type: "input_audio_buffer.clear" });
  emit(out, { type: "response_started" });
}

function onInputTranscript(s: RealtimeTurnState, out: Out, event: Record<string, unknown>): void {
  if (typeof event.item_id === "string" && event.item_id !== s.activeInputId) return;
  const text = liveTalkTranscriptText(event);
  const echoSource = s.lastAssistantText || s.assistantTranscript;
  if (s.suppressCurrentInputTurn || (!s.bargeIn && text && isLikelyAssistantEcho(text, echoSource))) {
    dropEchoInput(out, "echo-transcript", false);
    s.suppressCurrentInputTurn = false;
    log(out, "ignored-assistant-echo-transcript", text);
    return;
  }
  if (text && isLiveTalkSilenceHallucination(text)) {
    log(out, "ignored-silence-hallucination", text);
    return;
  }
  if (text) emit(out, { type: "user_transcript", text });
}

function onOutputAudioStopped(s: RealtimeTurnState, out: Out): void {
  s.sawOutputAudioStopped = true;
  if (s.bargeIn) {
    s.assistantSpeaking = false;
    clearMicResume(out);
    if (s.responseFinished) emit(out, { type: "response_done" });
    return;
  }
  startTimer(out, "mic_resume", LIVE_TALK_PLAYBACK_TAIL_MS, { type: "resume_mic" });
}

function onToolCalls(s: RealtimeTurnState, out: Out, calls: RealtimeFunctionCall[]): void {
  const fresh = calls.filter((call) => !s.completedToolCalls.has(call.call_id));
  s.completedToolCalls = new Set([...s.completedToolCalls, ...fresh.map((call) => call.call_id)]);
  if (!fresh.length) return;
  const runs = fresh.slice(0, MAX_TOOL_CALLS_PER_RESPONSE).map((call) => {
    s.toolCallsThisTurn += 1;
    return { call, withinLimit: s.toolCallsThisTurn <= MAX_LOOKUPS_PER_TURN };
  });
  out.push({ type: "run_tools", epoch: s.turnEpoch, turnId: s.activeInputId, calls: runs });
}

function onResponseDone(s: RealtimeTurnState, out: Out, event: Record<string, unknown>): void {
  const calls = realtimeFunctionCalls(event.response);
  if (calls.length > 0) {
    onToolCalls(s, out, calls);
    return;
  }
  s.suppressCurrentInputTurn = false;
  s.responseFinished = true;
  if (!s.bargeIn) send(out, { type: "input_audio_buffer.clear" });
  if (s.assistantSpeaking && !s.sawOutputAudioStopped) {
    // Barge-in persists only once playback ends: the user can still interrupt
    // buffered audio. Half duplex: generation finished but playout continues,
    // so the mic stays shut until the stop event or this fallback.
    const then: RealtimeTurnEvent = s.bargeIn ? { type: "playback_fallback" } : { type: "resume_mic" };
    startTimer(out, "mic_resume", PLAYBACK_UNMUTE_FALLBACK_MS, then);
    if (s.bargeIn) return;
  }
  emit(out, { type: "response_done" });
}

function onServerError(s: RealtimeTurnState, out: Out, event: Record<string, unknown>): void {
  clearMicResume(out);
  s.assistantSpeaking = false;
  s.suppressCurrentInputTurn = false;
  s.acceptedUserUtterance = false;
  syncMic(s, out);
  const rawError = event.error;
  const message =
    rawError && typeof rawError === "object" && "message" in rawError
      ? String((rawError as { message?: unknown }).message || "Realtime voice failed")
      : "Realtime voice failed";
  emitError(s, out, message);
}

function onServerEvent(s: RealtimeTurnState, out: Out, event: Record<string, unknown>, receivedAt: number): void {
  if (s.closed) return;
  const type = typeof event.type === "string" ? event.type : "";
  // Cancellation/transcript events for the interrupted response must not
  // complete or overwrite the next user's turn.
  const response = event.response as { id?: string; status?: string } | undefined;
  const responseId = typeof event.response_id === "string" ? event.response_id : response?.id;
  if (type !== "response.created" && responseId && responseId !== s.activeResponseId) return;
  log(out, "event", type);
  switch (type) {
    case "session.created":
      log(out, "session-created", sessionTurnSnapshot(event));
      startTimer(out, "session_ready", LIVE_TALK_CONNECT_WARMUP_MS, {
        type: "session_ready",
        reason: "session.created+warmup",
      });
      return;
    case "input_audio_buffer.speech_started":
      return onSpeechStarted(s, out, event, receivedAt);
    case "input_audio_buffer.speech_stopped":
      return onSpeechStopped(s, out);
    case "response.created":
      return onResponseCreated(s, out, response);
    case "conversation.item.input_audio_transcription.completed":
      return onInputTranscript(s, out, event);
    case "response.output_audio_transcript.delta":
    case "response.audio_transcript.delta": {
      const delta = liveTalkTranscriptText(event);
      if (!delta) return;
      s.assistantTranscript += delta;
      emit(out, { type: "assistant_transcript", text: s.assistantTranscript.trimStart(), final: false });
      return;
    }
    case "response.output_audio_transcript.done":
    case "response.audio_transcript.done": {
      s.assistantTranscript = liveTalkTranscriptText(event) || s.assistantTranscript;
      if (!s.assistantTranscript.trim()) return;
      s.lastAssistantText = s.assistantTranscript.trim();
      emit(out, { type: "assistant_transcript", text: s.lastAssistantText, final: true });
      return;
    }
    case "output_audio_buffer.stopped":
    case "output_audio_buffer.audio_stopped":
      return onOutputAudioStopped(s, out);
    case "response.done":
      return onResponseDone(s, out, event);
    case "error":
      return onServerError(s, out, event);
  }
}

function onToolOutput(
  s: RealtimeTurnState,
  out: Out,
  event: Extract<RealtimeTurnEvent, { type: "tool_output" }>,
): void {
  if (s.closed) return;
  const current = event.epoch === s.turnEpoch;
  send(out, {
    type: "conversation.item.create",
    item: {
      type: "function_call_output",
      call_id: event.callId,
      output: JSON.stringify(current ? event.result : { content: "Lookup cancelled by a new user turn." }),
    },
  });
  if (current && "sources" in event.result && event.result.sources?.length) {
    emit(out, { type: "search_sources", sources: event.result.sources });
  }
}

function onCancelResponse(s: RealtimeTurnState, out: Out): void {
  s.turnEpoch += 1;
  send(out, { type: "response.cancel" });
  if (s.bargeIn) send(out, { type: "output_audio_buffer.clear" });
  if (s.assistantSpeaking) emit(out, { type: "response_interrupted" });
  s.activeResponseId = null;
  s.assistantSpeaking = false;
  clearMicResume(out);
  syncMic(s, out);
}

/** Pure: the next turn state and the side effects the session performs, in order. */
export function reduceRealtimeTurn(state: RealtimeTurnState, event: RealtimeTurnEvent): RealtimeTurnStep {
  const s = { ...state };
  const out: Out = [];
  switch (event.type) {
    case "server_event":
      onServerEvent(s, out, event.event, event.receivedAt);
      break;
    case "channel_open":
      // Session turn_detection is minted server-side. Do not session.update
      // audio.input here — a nested replace can kill server VAD.
      startTimer(out, "session_ready", LIVE_TALK_SESSION_READY_FALLBACK_MS, {
        type: "session_ready",
        reason: "fallback",
      });
      emit(out, { type: "connected" });
      break;
    // A dropped network fails the peer: only closing stops the mic and frees the peer.
    case "peer_failed":
      if (!s.closed) emitError(s, out, event.message, true);
      break;
    case "channel_failed":
      emitError(s, out, event.message, true);
      break;
    case "session_ready":
      if (s.sessionReadyForTurns) break;
      s.sessionReadyForTurns = true;
      log(out, "session-ready-for-turns", event.reason);
      break;
    case "resume_mic":
      s.assistantSpeaking = false;
      syncMic(s, out);
      break;
    case "playback_fallback":
      s.assistantSpeaking = false;
      if (!s.closed) emit(out, { type: "response_done" });
      break;
    case "tool_output":
      onToolOutput(s, out, event);
      break;
    case "tools_settled":
      if (!s.closed && event.epoch === s.turnEpoch) send(out, { type: "response.create" });
      break;
    case "set_muted":
      s.userMuted = event.muted;
      syncMic(s, out);
      break;
    case "cancel_response":
      onCancelResponse(s, out);
      break;
    case "close":
      s.closed = true;
      break;
  }
  return { state: s, commands: out };
}
