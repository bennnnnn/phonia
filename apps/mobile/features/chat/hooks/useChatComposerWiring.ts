import { useCallback, useState, type MutableRefObject } from "react";

import type { UpgradeSource } from "@/features/billing/components/UpgradeSheet";
import type { User } from "@/lib/api";
import type { useChatScroll } from "@/features/chat/hooks/useChatScroll";
import type { useChatSend } from "@/features/chat/hooks/useChatSend";
import { useComposerDictation } from "@/features/chat/hooks/useComposerDictation";
import type { EditThread } from "@/features/chat/model/threadEdit";
import { useLiveTalk } from "@/features/speech/hooks/useLiveTalk";

type Options = {
  token: string | null;
  user: User | null;
  routeChatId: string | undefined;
  chatId: string | null;
  send: ReturnType<typeof useChatSend>;
  scroll: Pick<ReturnType<typeof useChatScroll>, "scrollToLatest" | "newMessageCountRef">;
  /** The open chat's id, or a new chat made the open one. */
  ensureChatId: () => Promise<string | null>;
  editThread: EditThread;
  isOffline: boolean;
  /** Bound once the render commits (ChatScreen): read when needed. */
  openUpgradeRef: MutableRefObject<((source?: UpgradeSource) => void) | null>;
  onFirstReplyRef: MutableRefObject<(id?: string | null) => Promise<void>>;
  t: (key: string) => string;
};

/**
 * What surrounds the composer on the chat screen: the mic, live talk, the attachment
 * sheet and the maths scanner, and the extra height the scanner bar and a grown input
 * take. ChatScreen lays them out; this hook wires them (structure ticket ST-08).
 */
export function useChatComposerWiring({
  token, user, routeChatId, chatId, send, scroll, ensureChatId, editThread, isOffline, openUpgradeRef,
  onFirstReplyRef, t,
}: Options) {
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

  // Live talk runs without a saved chat when none can be made, as it always has.
  const ensureLiveTalkChatId = useCallback(() => ensureChatId().catch(() => null), [ensureChatId]);
  const liveTalk = useLiveTalk({
    token,
    chatId,
    ensureChatId: ensureLiveTalkChatId,
    editThread,
    isOffline,
    onUpgrade: () => openUpgradeRef.current?.("live_talk"),
    onScrollToLatest: scroll.scrollToLatest,
    newMessageCountRef: scroll.newMessageCountRef,
    onFirstReply: (id?: string | null) => {
      void onFirstReplyRef.current(id);
    },
    t,
  });

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
    liveTalk,
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
      onLiveTalkPress: liveTalk.open,
    },
    liveTalkSession: liveTalk.visible
      ? {
          muted: liveTalk.muted,
          onClose: liveTalk.close,
          onMutePress: liveTalk.toggleMute,
          onYield: liveTalk.yieldToComposer,
        }
      : null,
  };
}
