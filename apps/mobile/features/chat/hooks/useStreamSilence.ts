import { useEffect, useState } from "react";

/** After the reply has started, this long without new text is worth saying. */
const STREAM_SILENCE_HINT_MS = 20_000;

/**
 * True once a reply that is showing text has not grown for `delayMs`. A
 * provider can stall mid-reply; the server gives up after its idle limit
 * (30 s in production), and until then frozen text and a caret looked hung.
 * Before the first token the typing indicator and status label cover the wait.
 */
export function useStreamSilence(
  contentLength: number,
  active: boolean,
  delayMs: number = STREAM_SILENCE_HINT_MS,
): boolean {
  // The length the reply had when it went quiet; any new text no longer matches.
  const [stalledAt, setStalledAt] = useState<number | null>(null);
  useEffect(() => {
    if (!active || contentLength === 0) return;
    const timer = setTimeout(() => setStalledAt(contentLength), delayMs);
    return () => clearTimeout(timer);
  }, [active, contentLength, delayMs]);
  return active && contentLength > 0 && stalledAt === contentLength;
}
