import { useCallback, useRef, useState, type MutableRefObject } from "react";
import { Keyboard, Linking } from "react-native";

import type { ActionFeedbackApi } from "@/contexts/actionFeedbackCore";
import type { AttachmentSource } from "@/features/attachments/components/AttachmentSourceSheet";
import { attachmentErrorMessage } from "@/features/attachments/model/attachmentErrors";
import {
  discardDraftAttachment,
  NativePickerBusyError,
  NativePickerTimeoutError,
  PhotoLibraryPermissionError,
  pickDocument,
  pickFromCamera,
  pickFromPhotoLibrary,
  type PendingAttachment,
} from "@/features/attachments/model/attachments";
import { getSessionGeneration } from "@/lib/auth";

type Options = {
  token: string | null;
  streaming: boolean;
  /** Account generation the composer was rendered for. */
  session: number;
  /** Bumped on every thread or account switch: a pick that outlives its view is dropped. */
  viewRef: MutableRefObject<{ version: number }>;
  /** A send is preparing; the composer takes no new attachment until it settles. */
  sendInFlightRef: MutableRefObject<boolean>;
  /** Puts the pick in the composer, freeing the file it replaces. */
  replacePendingAttachment: (next: PendingAttachment | null) => void;
  feedback: ActionFeedbackApi | null;
  t: (key: string, options?: Record<string, unknown>) => string;
};

function pickFrom(source: Exclude<AttachmentSource, "solve_math_camera">) {
  if (source === "camera") return pickFromCamera();
  if (source === "photo") return pickFromPhotoLibrary();
  return pickDocument();
}

/**
 * The composer's attach sheet and math scanner: which is open, and the pick each
 * source runs. A pick is "in flight" from the tap until its photo is prepared
 * (resized, re-encoded, size-checked), and Send waits: a send that slipped in
 * first went without the photo, which then turned up afterwards as a stray draft.
 */
export function useComposerAttachmentSheet({
  token,
  streaming,
  session,
  viewRef,
  sendInFlightRef,
  replacePendingAttachment,
  feedback,
  t,
}: Options) {
  const [attachSheetOpen, setAttachSheetOpen] = useState(false);
  const [mathScannerOpen, setMathScannerOpen] = useState(false);
  const [attachPicking, setAttachPicking] = useState(false);
  const attachPickInFlightRef = useRef(false);

  const handlePickAttachment = useCallback(() => {
    if (!token || streaming || sendInFlightRef.current || attachPickInFlightRef.current) return;
    Keyboard.dismiss();
    // Let the keyboard finish dismissing so the first tap isn't swallowed on Android.
    const version = viewRef.current.version;
    requestAnimationFrame(() => {
      if (viewRef.current.version === version && session === getSessionGeneration()) setAttachSheetOpen(true);
    });
  }, [token, streaming, session, viewRef, sendInFlightRef]);

  const handleAttachmentSheetSelect = useCallback(
    async (source: AttachmentSource) => {
      if (attachPickInFlightRef.current || !token || streaming || sendInFlightRef.current) return;
      setAttachSheetOpen(false);
      if (source === "solve_math_camera") {
        setMathScannerOpen(true);
        return;
      }
      const version = viewRef.current.version;
      const current = () => viewRef.current.version === version && session === getSessionGeneration();
      attachPickInFlightRef.current = true;
      setAttachPicking(true);
      try {
        const picked = await pickFrom(source);
        // A pick that lands after the user moved on belongs to no composer.
        if (picked && current()) replacePendingAttachment(picked);
        else discardDraftAttachment(null, picked);
      } catch (error) {
        if (!current()) return;
        if (error instanceof PhotoLibraryPermissionError) {
          if (error.needsSettings) void Linking.openSettings();
          feedback?.error(t("chat.photos_permission"));
        } else if (error instanceof NativePickerBusyError || error instanceof NativePickerTimeoutError) {
          feedback?.error(t("chat.picker_busy"));
        } else {
          feedback?.error(attachmentErrorMessage(error, t));
        }
      } finally {
        attachPickInFlightRef.current = false;
        setAttachPicking(false);
      }
    },
    [token, streaming, session, viewRef, sendInFlightRef, feedback, t, replacePendingAttachment],
  );

  return {
    attachSheetOpen,
    setAttachSheetOpen,
    mathScannerOpen,
    setMathScannerOpen,
    attachPicking,
    attachPickInFlightRef,
    handlePickAttachment,
    handleAttachmentSheetSelect,
  };
}
