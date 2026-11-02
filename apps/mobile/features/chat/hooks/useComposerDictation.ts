import { useCallback, useLayoutEffect, useRef, type Dispatch, type MutableRefObject, type SetStateAction } from "react";

import type { UpgradeSource } from "@/features/billing/components/UpgradeSheet";
import { composerThreadKey } from "@/features/chat/model/composerThreadDraft";
import { useVoiceInput } from "@/features/speech/hooks/useVoiceInput";
import type { User } from "@/lib/api";
import { hasPlanFeature } from "@/lib/plan";
import { useLatestRef } from "@/lib/latestRef";

type Options = {
  token: string | null;
  user: User | null;
  routeChatId: string | undefined;
  setInput: Dispatch<SetStateAction<string>>;
  /** Read when needed: the upgrade sheet is wired after this hook runs. */
  openUpgradeRef: MutableRefObject<((source?: UpgradeSource) => void) | null>;
  t: (key: string) => string;
};

/**
 * The composer mic: a take lands in the thread it was started in, a route
 * change drops the open take, and a plan without dictation opens the plans
 * instead of recording.
 */
export function useComposerDictation({
  token,
  user,
  routeChatId,
  setInput,
  openUpgradeRef,
  t,
}: Options) {
  const composerThread = composerThreadKey(
    typeof routeChatId === "string" ? routeChatId : undefined,
  );
  const composerThreadRef = useLatestRef(composerThread);
  const voiceCaptureThreadRef = useRef(composerThread);

  const {
    voiceInputAvailable,
    voiceRecording,
    voiceTranscribing,
    voiceMeterLevel,
    toggleVoiceInput,
    cancelVoiceInput,
  } = useVoiceInput({
    token,
    onTranscript: (text) => {
      if (voiceCaptureThreadRef.current !== composerThreadRef.current) return;
      setInput((prev) => (prev.trim() ? `${prev.trim()} ${text}` : text));
    },
    // The server refused: the plan has no voice input (the app's copy was stale).
    onPlanRequired: () => openUpgradeRef.current?.("voice"),
    t,
  });

  useLayoutEffect(() => {
    cancelVoiceInput();
  }, [routeChatId, cancelVoiceInput]);

  const canDictate = hasPlanFeature(user, "speech_transcription");
  const handleToggleVoiceInput = useCallback(() => {
    if (!voiceRecording && !voiceTranscribing) {
      // Don't record what the plan cannot send; show the plans instead.
      if (!canDictate) {
        openUpgradeRef.current?.("voice");
        return;
      }
      voiceCaptureThreadRef.current = composerThreadRef.current;
    }
    void toggleVoiceInput();
  }, [canDictate, toggleVoiceInput, voiceRecording, voiceTranscribing, openUpgradeRef, composerThreadRef]);

  return {
    voiceInputAvailable,
    voiceRecording,
    voiceTranscribing,
    voiceMeterLevel,
    toggleVoiceInput: handleToggleVoiceInput,
    cancelVoiceInput,
  };
}
