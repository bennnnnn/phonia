import { useCallback, useState, type MutableRefObject } from "react";

import type { UpgradeSource } from "@/features/billing/components/UpgradeSheet";
import type { User } from "@/lib/api";
import type { useChatSend } from "@/features/chat/hooks/useChatSend";
import { useComposerDictation } from "@/features/chat/hooks/useComposerDictation";

type Options = {
  token: string | null;
  user: User | null;
  routeChatId: string | undefined;
  send: ReturnType<typeof useChatSend>;
  /** Bound once the render commits (ChatScreen): read when needed. */
  openUpgradeRef: MutableRefObject<((source?: UpgradeSource) => void) | null>;
  t: (key: string) => string;
};

/**
 * What surrounds the composer on the chat screen: the mic, the attachment
 * sheet and the maths scanner, and the extra height the scanner bar and a grown input
 * take. ChatScreen lays them out; this hook wires them (structure ticket ST-08).
 */
export function useChatComposerWiring({ token, user, routeChatId, send, openUpgradeRef, t }: Options) {
  const [mathChromeExtra, setMathChromeExtra] = useState(0);
  const [composerInputExtra, setComposerInputExtra] = useState(0);

  const {
    voiceInputAvailable,
    voiceRecording,
    voiceTranscribing,
    voiceMeterLevel,
    toggleVoiceInput: handleToggleVoiceInput,
    cancelVoiceInput,
  } = useComposerDictation({ token, user, routeChatId, setInput: send.setInput, openUpgradeRef, t });

  const { setAttachSheetOpen, setMathScannerOpen } = send;
  const closeAttachSheet = useCallback(() => {
    setAttachSheetOpen(false);
  }, [setAttachSheetOpen]);

  const closeMathScanner = useCallback(() => {
    setMathScannerOpen(false);
  }, [setMathScannerOpen]);
  const openMathScanner = useCallback(() => {
    setMathScannerOpen(true);
  }, [setMathScannerOpen]);

  return {
    mathChromeExtra,
    composerInputExtra,
    attachments: {
      attachSheetOpen: send.attachSheetOpen,
      closeAttachSheet,
      attachPicking: send.attachPicking,
      pendingAttachment: send.pendingAttachment,
      removePendingAttachment: send.removePendingAttachment,
      handlePickAttachment: send.handlePickAttachment,
      handleAttachmentSheetSelect: send.handleAttachmentSheetSelect,
      mathScannerOpen: send.mathScannerOpen,
      closeMathScanner,
      handleMathScanCaptured: send.handleMathScanCaptured,
      readScan: send.readScan,
      handleMathScanSolve: send.handleMathScanSolve,
      onOpenMathScanner: openMathScanner,
      onMathChromeHeightChange: setMathChromeExtra,
      onInputFrameExtraChange: setComposerInputExtra,
    },
    voice: {
      voiceAvailable: voiceInputAvailable,
      voiceRecording,
      voiceTranscribing,
      voiceMeterLevel,
      toggleVoiceInput: handleToggleVoiceInput,
      cancelVoiceInput,
    },
  };
}
