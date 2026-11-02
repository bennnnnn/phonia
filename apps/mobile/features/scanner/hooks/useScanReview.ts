import { useCallback, useEffect, useRef, useState } from "react";

import type { ScanReadingState } from "@/features/scanner/components/ScanReadingReview";
import type { PendingAttachment } from "@/features/attachments/model/attachments";
import type { ScanReading } from "@/lib/api";
import { type ReadBackSubject, readsBack } from "@/features/scanner/model/readBack";
import type { ScanFiles } from "@/features/scanner/model/scanImage";
import type { ScannerSubject } from "@/lib/scanner/subjects";

/** The subject is the one the crop was read with, not whatever is selected later. */
type ScanReview = { shot: PendingAttachment; subject: ReadBackSubject; state: ScanReadingState };

type Args = {
  visible: boolean;
  files: ScanFiles;
  onCaptured: (pending: PendingAttachment, subject: ScannerSubject, confirmedReading?: string) => void;
  onReadScan?: (
    scan: PendingAttachment,
    subject: ReadBackSubject,
    signal: AbortSignal,
  ) => Promise<ScanReading | { error: string } | null>;
  onSolveReading?: (reading: string, subject: ScannerSubject) => void;
};

function settledState(result: ScanReading | { error: string } | null): ScanReadingState {
  if (result && "reading" in result && result.reading.trim()) {
    return { status: "ready", reading: result.reading.trim(), uncertain: result.uncertain };
  }
  const message = result && "error" in result ? result.error : "";
  return { status: "failed", ...(message ? { message } : {}) };
}

/**
 * What happens to a crop: a read-back subject is read for the student to
 * check ("I read this as"), anything else goes straight to the chat. The crop
 * file is handed to the composer only when it becomes the chat attachment.
 */
export function useScanReview({ visible, files, onCaptured, onReadScan, onSolveReading }: Args) {
  const [review, setReview] = useState<ScanReview | null>(null);
  const readAbortRef = useRef<AbortController | null>(null);
  const stopReading = useCallback(() => {
    readAbortRef.current?.abort();
    readAbortRef.current = null;
  }, []);

  useEffect(() => {
    if (!visible) stopReading();
  }, [stopReading, visible]);
  useEffect(() => stopReading, [stopReading]);

  /** The crop becomes the chat attachment; every other scan file goes. */
  const handOffShot = useCallback(
    (shot: PendingAttachment) => {
      files.handOff(shot.localUri);
      files.discardAll();
    },
    [files],
  );

  /** Deliver a fresh crop. Returns true when it opened the review. */
  const deliverShot = useCallback(
    (shot: PendingAttachment, subject: ScannerSubject): boolean => {
      if (!readsBack(subject) || !onReadScan || !onSolveReading) {
        handOffShot(shot);
        onCaptured(shot, subject);
        return false;
      }
      stopReading();
      const controller = new AbortController();
      readAbortRef.current = controller;
      setReview({ shot, subject, state: { status: "reading" } });
      void onReadScan(shot, subject, controller.signal)
        .catch(() => null)
        .then((result) => {
          if (controller.signal.aborted) return;
          readAbortRef.current = null;
          setReview((current) =>
            current && current.shot === shot ? { ...current, state: settledState(result) } : current,
          );
        });
      return true;
    },
    [handOffShot, onCaptured, onReadScan, onSolveReading, stopReading],
  );

  const clearReview = useCallback(() => {
    stopReading();
    setReview(null);
  }, [stopReading]);

  const solve = useCallback(
    (reading: string) => {
      if (!review) return;
      stopReading();
      // Solved as text: the crop is not sent, so it is not kept.
      files.discardAll();
      onSolveReading?.(reading, review.subject);
    },
    [files, onSolveReading, review, stopReading],
  );

  const sendPhoto = useCallback(
    (reading: string) => {
      if (!review) return;
      stopReading();
      // Math and physics carry the checked reading so the API solves that;
      // chemistry solves from the photo with the reading alongside.
      handOffShot(review.shot);
      onCaptured(review.shot, review.subject, reading || undefined);
    },
    [handOffShot, onCaptured, review, stopReading],
  );

  return { review, deliverShot, clearReview, solve, sendPhoto };
}
