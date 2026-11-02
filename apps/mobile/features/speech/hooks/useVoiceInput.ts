import { useCallback, useEffect, useRef, useState } from "react";
import { Linking } from "react-native";
import { useSharedValue } from "react-native-reanimated";

import { transcribeSpeech } from "@/lib/api";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { voiceRefusalKey } from "@/features/speech/model/voiceRefusal";
import {
  deleteVoiceRecording,
  isVoiceInputAvailable,
  loadExpoAudio,
  requestVoicePermission,
  startVoiceRecording,
  VOICE_MAX_RECORDING_MS,
  type VoiceRecorder,
} from "@/lib/speech/voiceAudio";
import { confirmDialog } from "@/ui/overlay/dialogs";

type Options = {
  token: string | null;
  onTranscript: (text: string) => void;
  t: (key: string) => string;
  /** The server said the plan has no voice input (HTTP 403): show the plans. */
  onPlanRequired?: () => void;
};

function errorStatus(error: unknown): unknown {
  return error && typeof error === "object" && "status" in error
    ? (error as { status: unknown }).status
    : undefined;
}

const VOICE_SPEECH_LEVEL = 0.28;
const VOICE_MIN_SPEECH_SAMPLES = 2;

export function useVoiceInput({
  token,
  onTranscript,
  t,
  onPlanRequired,
}: Options) {
  const feedback = useActionFeedbackOptional();
  const recordingRef = useRef<VoiceRecorder | null>(null);
  const meterUnsubRef = useRef<(() => void) | null>(null);
  const maxTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finishRecordingRef = useRef<() => Promise<string | null>>(async () => null);
  const speechSamplesRef = useRef(0);
  const captureGenRef = useRef(0);
  /** A start is awaiting permission or the native recorder. */
  const startingRef = useRef(false);
  const transcribeAbortRef = useRef<AbortController | null>(null);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  // The live level, every 60 ms while dictating: a shared value only the waveform reads.
  // As state it re-rendered the whole chat screen 16 times a second.
  const meterLevel = useSharedValue(0.12);
  const [voiceInputAvailable, setVoiceInputAvailable] = useState(false);

  useEffect(() => {
    setVoiceInputAvailable(isVoiceInputAvailable());
  }, []);

  const showUnavailable = useCallback(() => {
    reportRecoverableError(feedback, t("chat.voice_unavailable_body"));
  }, [feedback, t]);

  const stopRecording = useCallback(async (): Promise<string | null> => {
    if (maxTimerRef.current != null) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }
    const active = recordingRef.current;
    recordingRef.current = null;
    meterUnsubRef.current?.();
    meterUnsubRef.current = null;
    setRecording(false);
    meterLevel.set(0.12);
    if (!active) return null;
    try {
      return await active.stop();
    } catch {
      return null;
    }
  }, [meterLevel]);

  const startRecording = useCallback(async (): Promise<boolean> => {
    // `recording` only turns true once the native recorder runs, so a second
    // tap meanwhile would open a second recorder that nothing ever stops.
    if (!token || recording || transcribing || startingRef.current) return false;
    startingRef.current = true;
    // Cancel and unmount bump this; a start that resolves after either must
    // release the mic itself, because no one is left to stop it.
    const gen = captureGenRef.current;
    try {
      const mod = loadExpoAudio();
      if (!mod) {
        showUnavailable();
        return false;
      }
      const permission = await requestVoicePermission(mod);
      if (gen !== captureGenRef.current) return false;
      if (!permission.granted) {
        // The OS asks only once; after a denial only Settings can turn it on.
        void confirmDialog({
          title: t("chat.voice_permission_title"),
          message: t("chat.voice_permission_body"),
          cancelLabel: t("common.cancel"),
          confirmLabel: t("chat.location_open_settings"),
        }).then((open) => {
          if (open) void Linking.openSettings();
        });
        return false;
      }
      const next = await startVoiceRecording();
      if (gen !== captureGenRef.current) {
        if (next) void next.stop().then(deleteVoiceRecording).catch(() => undefined);
        return false;
      }
      if (!next) {
        showUnavailable();
        return false;
      }
      speechSamplesRef.current = 0;
      recordingRef.current = next;
      meterUnsubRef.current?.();
      meterUnsubRef.current = next.subscribeMetering((level) => {
        meterLevel.set(level);
        if (level >= VOICE_SPEECH_LEVEL) speechSamplesRef.current += 1;
      });
      setRecording(true);
      if (maxTimerRef.current != null) clearTimeout(maxTimerRef.current);
      maxTimerRef.current = setTimeout(() => {
        void finishRecordingRef.current();
      }, VOICE_MAX_RECORDING_MS);
      return true;
    } catch {
      if (gen === captureGenRef.current) {
        reportRecoverableError(feedback, t("chat.voice_start_failed"));
      }
      return false;
    } finally {
      startingRef.current = false;
    }
  }, [token, recording, transcribing, t, showUnavailable, feedback, meterLevel]);

  const finishRecording = useCallback(async (): Promise<string | null> => {
    if (!token) return null;
    const gen = captureGenRef.current;
    setTranscribing(true);
    const heardSpeech = speechSamplesRef.current >= VOICE_MIN_SPEECH_SAMPLES;
    const uri = await stopRecording();
    if (gen !== captureGenRef.current || !uri || !heardSpeech) void deleteVoiceRecording(uri);
    if (gen !== captureGenRef.current) return null;
    if (!uri || !heardSpeech) {
      setTranscribing(false);
      reportRecoverableError(feedback, t("chat.voice_recording_empty"));
      return null;
    }
    const controller = new AbortController();
    transcribeAbortRef.current = controller;
    try {
      const text = await transcribeSpeech(token, uri, controller.signal);
      if (gen !== captureGenRef.current) return null;
      onTranscript(text);
      return text;
    } catch (error) {
      if (gen !== captureGenRef.current) return null;
      if (errorStatus(error) === 403 && onPlanRequired) {
        onPlanRequired();
        return null;
      }
      const message = error instanceof Error ? error.message : "";
      const refusal = voiceRefusalKey(error);
      if (refusal) {
        reportRecoverableError(feedback, t(refusal));
      } else if (/network request failed|failed to fetch|timeout|timed out|could not reach/i.test(message)) {
        reportRecoverableError(feedback, t("chat.voice_network_failed"));
      } else if (message.includes("recording_empty")) {
        reportRecoverableError(feedback, t("chat.voice_recording_empty"));
      } else if (message.includes("transcribe_empty")) {
        reportRecoverableError(feedback, t("chat.voice_transcribe_empty"));
      } else {
        reportRecoverableError(feedback, t("chat.voice_transcribe_failed"));
      }
      return null;
    } finally {
      // Sent or not, the recording is not kept (code-health audit LEAK-04).
      void deleteVoiceRecording(uri);
      if (transcribeAbortRef.current === controller) transcribeAbortRef.current = null;
      if (gen === captureGenRef.current) setTranscribing(false);
    }
  }, [token, stopRecording, onTranscript, onPlanRequired, feedback, t]);

  finishRecordingRef.current = finishRecording;

  const cancelVoiceInput = useCallback(() => {
    captureGenRef.current += 1;
    transcribeAbortRef.current?.abort();
    transcribeAbortRef.current = null;
    void stopRecording().then(deleteVoiceRecording);
    setTranscribing(false);
  }, [stopRecording]);

  const toggleRecording = useCallback(async () => {
    if (transcribing) return;
    if (!voiceInputAvailable) {
      showUnavailable();
      return;
    }
    if (recording) {
      await finishRecording();
      return;
    }
    await startRecording();
  }, [
    transcribing,
    voiceInputAvailable,
    recording,
    finishRecording,
    startRecording,
    showUnavailable,
  ]);

  useEffect(() => {
    return () => {
      // A start still awaiting the recorder stops it when it arrives.
      captureGenRef.current += 1;
      transcribeAbortRef.current?.abort();
      transcribeAbortRef.current = null;
      if (maxTimerRef.current != null) {
        clearTimeout(maxTimerRef.current);
        maxTimerRef.current = null;
      }
      meterUnsubRef.current?.();
      meterUnsubRef.current = null;
      const active = recordingRef.current;
      recordingRef.current = null;
      if (active) {
        void active.stop().then(deleteVoiceRecording).catch(() => undefined);
      }
    };
  }, []);

  return {
    voiceInputAvailable,
    voiceRecording: recording,
    voiceTranscribing: transcribing,
    voiceMeterLevel: meterLevel,
    toggleVoiceInput: toggleRecording,
    startRecording,
    finishRecording,
    cancelVoiceInput,
  };
}
