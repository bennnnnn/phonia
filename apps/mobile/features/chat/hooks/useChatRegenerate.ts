import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ClientGeo } from "@/features/chat/model/clientGeo";
import type { Message, User } from "@/lib/api";
import { resolveClientGeoForQuery } from "@/features/chat/model/resolveClientGeoForQuery";

type Params = {
  token: string | null;
  messages: Message[];
  updateUser: (patch: Partial<User>) => Promise<void>;
  regenerateResponse: (model?: string | null, clientGeo?: ClientGeo | null) => Promise<void>;
  /** Show typing before geo; optional guard invalidates preparation on Stop/navigation. */
  beginRegenerateUi?: () => (() => boolean) | void;
  /** Restore the prior assistant when geo is cancelled. */
  cancelRegenerateUi?: () => void;
};

export function useChatRegenerate({
  token,
  messages,
  updateUser,
  regenerateResponse,
  beginRegenerateUi,
  cancelRegenerateUi,
}: Params) {
  const { t } = useTranslation();
  const [regenerating, setRegenerating] = useState(false);
  const inFlightRef = useRef(false);

  const regenerate = useCallback(
    async (model: string) => {
      if (!token || inFlightRef.current) return;
      inFlightRef.current = true;
      setRegenerating(true);
      const isCurrentAttempt = beginRegenerateUi?.();
      try {
        // A reply is still coming: no regenerate, and no location prompt for one.
        if (isCurrentAttempt && !isCurrentAttempt()) return;
        const lastUser = [...messages].reverse().find((m) => m.role === "user");
        const result = await resolveClientGeoForQuery(
          token,
          lastUser?.content ?? "",
          t,
          updateUser,
        );
        if (isCurrentAttempt && !isCurrentAttempt()) return;
        if (!result.ok) {
          cancelRegenerateUi?.();
          return;
        }
        await regenerateResponse(model, result.clientGeo);
      } finally {
        inFlightRef.current = false;
        setRegenerating(false);
      }
    },
    [
      token,
      messages,
      regenerateResponse,
      beginRegenerateUi,
      cancelRegenerateUi,
      t,
      updateUser,
    ],
  );

  return { regenerate, regenerating };
}
