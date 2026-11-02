import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import { AppState, BackHandler, Linking } from "react-native";

import { useDrawerControls } from "@/contexts/DrawerContext";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { api } from "@/lib/api";
import type { Message } from "@/lib/api";
import { applyLiveTalkChatEvent, type LiveTalkSpeakEvent } from "@/features/speech/model/liveTalkEvents";
import {
  liveTalkCallErrorKey,
  liveTalkErrorGate,
  liveTalkGateMessageKey,
  liveTalkSessionLimitMs,
  liveTalkGate,
  liveTalkSaveEndsCall,
  liveTalkSaveFailedKey,
  liveTalkShouldAttachSession,
  liveTalkShouldCloseOnAppState,
  liveTalkShouldCloseOnChatChange,
  type LiveTalkGate,
  type LiveTalkPhase,
  type LiveTalkStatus,
} from "@/features/speech/model/liveTalkLogic";
import type { RealtimeVoiceEvent, RealtimeVoiceSession } from "@/features/speech/model/realtimeVoice";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { confirmDialog } from "@/ui/overlay/dialogs";

/**
 * What live talk takes from the chat screen it runs on: the chat a turn lands in and
 * how its bubbles show. Speech owns this shape, so it never imports the chat feature
 * (code-health audit ARCH-10).
 */
type Options = {
  token: string | null;
  chatId: string | null;
  /** The open chat's id, or a new chat made the open one; null when none could be made. */
  ensureChatId: () => Promise<string | null>;
  /** Changes the thread on screen, which the chat owns: live talk's turns, named "live_talk". */
  editThread: (update: SetStateAction<Message[]>, source: "live_talk") => void;
  isOffline: boolean;
  onUpgrade: () => void;
  onScrollToLatest: () => void;
  newMessageCountRef: MutableRefObject<number>;
  onFirstReply: (chatId?: string | null) => void;
  t: (key: string) => string;
};

type CompletedTurn = {
  id: string;
  chatId: string | null;
  callId: string | null;
  userText: string;
  assistantText: string;
};

const REALTIME_TRANSCRIPT_GRACE_MS = 350;

// The WebRTC session, its turn state and the chimes load when Live Talk is
// started, not with the chat screen. The hook itself stays static.
function loadRealtimeVoice() {
  return import("@/features/speech/model/realtimeVoice");
}

/** Best-effort, as the cue itself is: a chime that cannot load never fails Live Talk. */
function playCue(kind: "start" | "end"): Promise<void> {
  return import("@/features/speech/model/liveTalkSfx")
    .then(({ playLiveTalkCue }) => playLiveTalkCue(kind))
    .catch(() => {});
}

export function useLiveTalk({
  token,
  chatId,
  ensureChatId,
  editThread,
  isOffline,
  onUpgrade,
  onScrollToLatest,
  newMessageCountRef,
  onFirstReply,
  t,
}: Options) {
  const feedback = useActionFeedbackOptional();
  // Read when Back is pressed, not subscribed: the chat screen that calls this
  // hook must not render again every time the drawer opens or closes.
  const drawer = useDrawerControls();
  const [visible, setVisible] = useState(false);
  const [phase, setPhase] = useState<LiveTalkPhase>("idle");
  const [muted, setMuted] = useState(false);
  const [status, setStatus] = useState<LiveTalkStatus | null>(null);
  const sessionRef = useRef<RealtimeVoiceSession | null>(null);
  const callIdRef = useRef<string | null>(null);
  const turnIdRef = useRef("");
  const turnChatIdRef = useRef<string | null>(null);
  const assistantTextRef = useRef("");
  const sourcesRef = useRef<Message["search_sources"]>([]);
  const userTextRef = useRef("");
  const visibleRef = useRef(false);
  const sessionGenRef = useRef(0);
  const finishTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionLimitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeRef = useRef<() => void>(() => {});

  const alertForGate = useCallback(
    (gate: LiveTalkGate) => {
      if (gate === "upgrade") {
        onUpgrade();
        return;
      }
      // The API client already sent the account to the consent step.
      if (gate === "consent") return;
      if (gate === "mic_permission") {
        // The OS asks only once; after a denial only Settings can turn it on.
        void confirmDialog({
          title: t("chat.live_talk_mic_permission_title"),
          message: t("chat.live_talk_mic_permission_body"),
          cancelLabel: t("common.cancel"),
          confirmLabel: t("chat.location_open_settings"),
        }).then((open) => {
          if (open) void Linking.openSettings();
        });
        return;
      }
      reportRecoverableError(feedback, t(liveTalkGateMessageKey(gate)));
    },
    [feedback, onUpgrade, t],
  );

  const applyEvent = useCallback(
    (event: LiveTalkSpeakEvent, turnId = turnIdRef.current) => {
      if (!turnId) return;
      editThread((prev) => applyLiveTalkChatEvent(prev, turnId, event), "live_talk");
    },
    [editThread],
  );

  const captureCurrentTurn = useCallback((): CompletedTurn | null => {
    const id = turnIdRef.current;
    if (!id) return null;
    const completed: CompletedTurn = {
      id,
      chatId: turnChatIdRef.current,
      callId: callIdRef.current,
      userText: userTextRef.current.trim(),
      assistantText: assistantTextRef.current.trim(),
    };
    turnIdRef.current = "";
    userTextRef.current = "";
    assistantTextRef.current = "";
    return completed;
  }, []);

  const finishTurn = useCallback(
    async (completed: CompletedTurn) => {
      newMessageCountRef.current += Number(Boolean(completed.userText)) + Number(Boolean(completed.assistantText));
      onScrollToLatest();
      // Persistence, title generation, memory extraction, todo extraction, and
      // RAG indexing stay outside the audio path. Snapshot the completed turn
      // so a later utterance cannot mutate what gets saved.
      if (token && completed.chatId && completed.callId && (completed.userText || completed.assistantText)) {
        void api
          .persistRealtimeLiveTalkTurn(token, {
            chatId: completed.chatId,
            callId: completed.callId,
            userText: completed.userText,
            assistantText: completed.assistantText,
            turnId: completed.id,
          })
          .then((saved) => {
            // Reconcile this turn in place, never replace the whole thread
            // with a delayed list fetch while the next utterance is streaming.
            if (saved) applyEvent({ type: "done", remaining: 0, limit: 0,
              user_message: saved.user_message, assistant_message: saved.assistant_message }, completed.id);
          })
          .catch((error: unknown) => {
            const gate = liveTalkErrorGate(error);
            if (!liveTalkSaveEndsCall(gate)) {
              reportRecoverableError(feedback, t(liveTalkSaveFailedKey(gate)));
            } else if (callIdRef.current === completed.callId) {
              // Once: the hang-up's own save of the last turn is refused the same way.
              closeRef.current();
              alertForGate(gate);
            }
          });
      }

      try {
        const next = token ? await api.liveTalkStatus(token) : status;
        if (next) setStatus(next);
        applyEvent(
          {
            type: "done",
            remaining: next?.remaining ?? status?.remaining ?? 0,
            limit: next?.limit ?? status?.limit ?? 0,
            user_message: null,
            assistant_message: null,
          },
          completed.id,
        );
        onFirstReply(completed.chatId);
      } catch {
        // Voice already succeeded. A status refresh failure must not make the
        // completed turn look failed.
        applyEvent(
          {
            type: "done",
            remaining: status?.remaining ?? 0,
            limit: status?.limit ?? 0,
            user_message: null,
            assistant_message: null,
          },
          completed.id,
        );
      }
    },
    [alertForGate, applyEvent, feedback, newMessageCountRef, onFirstReply, onScrollToLatest, status, t, token],
  );

  const finalizeCurrentTurn = useCallback(() => {
    const completed = captureCurrentTurn();
    if (!completed) return;
    setPhase("idle");
    void finishTurn(completed);
  }, [captureCurrentTurn, finishTurn]);

  const flushPendingTurn = useCallback(() => {
    if (finishTimerRef.current != null) {
      clearTimeout(finishTimerRef.current);
      finishTimerRef.current = null;
    }
    if (turnIdRef.current && (userTextRef.current || assistantTextRef.current)) {
      finalizeCurrentTurn();
    }
  }, [finalizeCurrentTurn]);

  const handleRealtimeEvent = useCallback(
    (event: RealtimeVoiceEvent) => {
      const dropped = !visibleRef.current && event.type !== "connected";
      if (dropped) return;
      if (event.type === "connected") {
        setPhase("recording");
        return;
      }
      if (event.type === "speech_started") {
        // A new accepted utterance while the prior turn is still flushing:
        // persist that snapshot before starting a new one.
        flushPendingTurn();
        turnIdRef.current = event.turnId ?? String(Date.now());
        userTextRef.current = "";
        assistantTextRef.current = "";
        sourcesRef.current = [];
        setPhase("recording");
        return;
      }
      if (event.type === "response_interrupted") {
        // Realtime transcripts can run ahead of audio playback. There is no
        // reliable client word-to-audio alignment; don't save unspoken text
        // as if it was delivered. OpenAI truncates its own conversation buffer.
        assistantTextRef.current = t("chat.generation_stopped");
        applyEvent({ type: "assistant", text: assistantTextRef.current });
        flushPendingTurn();
        setPhase("recording");
        return;
      }
      if (event.type === "search_sources") {
        sourcesRef.current = event.sources;
        if (assistantTextRef.current) applyEvent({ type: "assistant", text: assistantTextRef.current, sources: event.sources });
        return;
      }
      if (event.type === "speech_stopped") {
        setPhase("thinking");
        return;
      }
      if (event.type === "response_started") {
        if (!turnIdRef.current) turnIdRef.current = String(Date.now());
        setPhase("thinking");
        return;
      }
      if (event.type === "user_transcript") {
        if (!turnIdRef.current) turnIdRef.current = String(Date.now());
        userTextRef.current = event.text;
        applyEvent({ type: "user", text: event.text });
        return;
      }
      if (event.type === "assistant_transcript") {
        if (!turnIdRef.current) turnIdRef.current = String(Date.now());
        assistantTextRef.current = event.text;
        applyEvent({ type: "assistant", text: event.text, sources: sourcesRef.current });
        setPhase("speaking");
        return;
      }
      if (event.type === "response_done") {
        if (finishTimerRef.current != null) clearTimeout(finishTimerRef.current);
        // This grace affects only persistence/UI canonicalization, never audible
        // audio. It allows the final input-transcription event to arrive if it
        // trails response.done by a few network frames.
        finishTimerRef.current = setTimeout(() => {
          finishTimerRef.current = null;
          finalizeCurrentTurn();
        }, REALTIME_TRANSCRIPT_GRACE_MS);
        return;
      }
      if (event.type === "error") {
        reportRecoverableError(feedback, t(liveTalkCallErrorKey(event.fatal)));
        setPhase("idle");
        // The connection is gone: left open, the mic kept recording into a dead peer.
        if (event.fatal) closeRef.current();
      }
    },
    [applyEvent, feedback, finalizeCurrentTurn, flushPendingTurn, t],
  );

  const close = useCallback(() => {
    sessionGenRef.current += 1;
    const shouldCueEnd = visibleRef.current || sessionRef.current != null;
    visibleRef.current = false;
    if (finishTimerRef.current != null) {
      clearTimeout(finishTimerRef.current);
      finishTimerRef.current = null;
    }
    if (sessionLimitTimerRef.current != null) {
      clearTimeout(sessionLimitTimerRef.current);
      sessionLimitTimerRef.current = null;
    }
    const completed = captureCurrentTurn();
    if (completed && (completed.userText || completed.assistantText)) {
      void finishTurn(completed);
    }
    sessionRef.current?.close();
    // Settle this month's minutes to the time actually used (best-effort: a
    // session never reported stays charged for its whole reservation).
    const endedCallId = callIdRef.current;
    if (token && endedCallId) {
      void api
        .endRealtimeSession(token, endedCallId)
        .then((next) => setStatus(next))
        .catch(() => {});
    }
    sessionRef.current = null;
    callIdRef.current = null;
    setMuted(false);
    setPhase("idle");
    setVisible(false);
    if (shouldCueEnd) void playCue("end");
  }, [captureCurrentTurn, finishTurn, token]);
  closeRef.current = close;

  const open = useCallback(async () => {
    if (!token) return;
    if (isOffline) {
      alertForGate("offline");
      return;
    }
    const voice = await loadRealtimeVoice().catch(() => null);
    if (!voice?.isRealtimeVoiceAvailable()) {
      alertForGate("unavailable");
      return;
    }
    const gen = sessionGenRef.current + 1;
    sessionGenRef.current = gen;
    try {
      const next = await api.liveTalkStatus(token);
      if (!liveTalkShouldAttachSession(gen, sessionGenRef.current)) return;
      setStatus(next);
      const gate = liveTalkGate(next, isOffline);
      if (gate !== "ok") {
        alertForGate(gate);
        return;
      }
      const activeChatId = await ensureChatId();
      if (!liveTalkShouldAttachSession(gen, sessionGenRef.current)) return;
      turnChatIdRef.current = activeChatId;
      visibleRef.current = true;
      setMuted(false);
      setPhase("thinking");
      setVisible(true);
      // Finish and release the open chime before getUserMedia. A leftover
      // expo-audio player keeps the session in playback and WebRTC is mute.
      await playCue("start");
      if (!liveTalkShouldAttachSession(gen, sessionGenRef.current)) return;
      const session = await voice.createRealtimeVoiceSession({
        token,
        chatId: activeChatId,
        onEvent: handleRealtimeEvent,
      });
      if (!liveTalkShouldAttachSession(gen, sessionGenRef.current)) {
        session.close();
        if (session.callId) void api.endRealtimeSession(token, session.callId).catch(() => {});
        return;
      }
      sessionRef.current = session;
      callIdRef.current = session.callId;
      if (sessionLimitTimerRef.current != null) {
        clearTimeout(sessionLimitTimerRef.current);
      }
      sessionLimitTimerRef.current = setTimeout(() => {
        sessionLimitTimerRef.current = null;
        closeRef.current();
      }, liveTalkSessionLimitMs(session.maxDurationSeconds));
      setPhase("recording");
    } catch (error) {
      if (!liveTalkShouldAttachSession(gen, sessionGenRef.current)) return;
      visibleRef.current = false;
      setVisible(false);
      setPhase("idle");
      alertForGate(liveTalkErrorGate(error));
    }
  }, [token, isOffline, alertForGate, ensureChatId, handleRealtimeEvent]);

  const toggleMute = useCallback(() => {
    const next = !muted;
    setMuted(next);
    sessionRef.current?.setMuted(next);
  }, [muted]);

  // Half-duplex: VAD still chunks speech; the client starts each reply.
  // interrupt_response stays off so echo cannot barge into playback.
  const toggle = useCallback(async () => {
    if (phase === "thinking") {
      sessionRef.current?.cancelResponse();
      setPhase("idle");
    }
  }, [phase]);

  const yieldToComposer = useCallback(() => {
    close();
  }, [close]);

  useEffect(() => {
    if (!visible) return;
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      if (drawer.isOpenNow()) return false;
      close();
      return true;
    });
    return () => sub.remove();
  }, [visible, drawer, close]);

  useEffect(() => {
    if (!liveTalkShouldCloseOnChatChange(turnChatIdRef.current, chatId)) return;
    close();
  }, [chatId, close]);

  useEffect(() => {
    if (!visible) return;
    const sub = AppState.addEventListener("change", (state) => {
      if (liveTalkShouldCloseOnAppState(state)) closeRef.current();
    });
    return () => sub.remove();
  }, [visible]);

  useEffect(() => {
    // Fast Refresh preserves `visible` and drops the native peer. A leftover
    // overlay with no session looks like Live Talk is on and hears nothing.
    if (visible && !sessionRef.current) {
      visibleRef.current = false;
      setVisible(false);
      setPhase("idle");
    }
    return () => closeRef.current();
  }, []);

  return {
    visible,
    phase,
    recording: phase === "recording",
    muted,
    open,
    close,
    toggle,
    toggleMute,
    yieldToComposer,
  };
}
