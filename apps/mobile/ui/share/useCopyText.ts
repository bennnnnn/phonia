import { useCallback, useEffect, useRef, useState } from "react";
import { setStringAsync } from "expo-clipboard";

import { notifySuccess } from "@/lib/haptics";

/** How long every copy control shows its check after copying. */
const COPIED_MS = 1500;

/**
 * Copy text and show the check: one timing and one success haptic for every copy
 * control (a reply's Copy, a code block's, the share sheet's). A copy the system
 * refuses is not thrown: `copy` resolves false and `onFailed` says so.
 */
export function useCopyText(onFailed?: () => void) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const failed = useRef(onFailed);
  failed.current = onFailed;

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const copy = useCallback(async (text: string): Promise<boolean> => {
    if (!text.trim()) return false;
    try {
      await setStringAsync(text);
    } catch {
      failed.current?.();
      return false;
    }
    notifySuccess();
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      setCopied(false);
    }, COPIED_MS);
    return true;
  }, []);

  /** Clears the check at once (a sheet opening again). */
  const reset = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setCopied(false);
  }, []);

  return { copied, copy, reset };
}
