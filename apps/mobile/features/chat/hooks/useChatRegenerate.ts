import { useCallback, useRef, useState } from "react";

type Params = {
  token: string | null;
  regenerateResponse: () => Promise<void>;
  /** Shows typing at the tap; the guard it returns says whether this attempt still stands. */
  beginRegenerateUi?: () => (() => boolean) | void;
};

export function useChatRegenerate({ token, regenerateResponse, beginRegenerateUi }: Params) {
  const [regenerating, setRegenerating] = useState(false);
  const inFlightRef = useRef(false);

  const regenerate = useCallback(async () => {
    if (!token || inFlightRef.current) return;
    inFlightRef.current = true;
    setRegenerating(true);
    const isCurrentAttempt = beginRegenerateUi?.();
    try {
      // A reply is still coming: no regenerate.
      if (isCurrentAttempt && !isCurrentAttempt()) return;
      await regenerateResponse();
    } finally {
      inFlightRef.current = false;
      setRegenerating(false);
    }
  }, [token, regenerateResponse, beginRegenerateUi]);

  return { regenerate, regenerating };
}
