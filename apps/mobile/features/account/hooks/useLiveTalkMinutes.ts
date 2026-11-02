import { useCallback, useRef, useState } from "react";
import { useFocusEffect } from "expo-router";

import { useAuthToken } from "@/contexts/AuthContext";
import { useReconnectRefresh } from "@/hooks/useReconnectRefresh";
import { api } from "@/lib/api";

/**
 * This month's live talk minutes left, read whenever the screen is shown and once more when
 * the API answers after an outage, while it has focus, unless a read landed since the
 * connection was lost (hooks/useReconnectRefresh.ts).
 */
export function useLiveTalkMinutes(enabled: boolean): { remaining: number; limit: number } | null {
  const token = useAuthToken();
  const [minutes, setMinutes] = useState<{ remaining: number; limit: number } | null>(null);
  // Bumped when the screen loses focus: a read from before lands nowhere.
  const visit = useRef(0);
  const landedAt = useRef<number | undefined>(undefined);

  const read = useCallback(() => {
    if (!enabled || !token) {
      setMinutes(null);
      return;
    }
    const current = visit.current;
    void api
      .liveTalkStatus(token)
      .then((status) => {
        landedAt.current = Date.now();
        if (current === visit.current && status.entitled) {
          setMinutes({ remaining: status.remaining, limit: status.limit });
        }
      })
      .catch(() => {
        // The row simply stays hidden; live talk itself re-checks on open.
      });
  }, [enabled, token]);

  useFocusEffect(
    useCallback(() => {
      read();
      return () => {
        visit.current += 1;
      };
    }, [read]),
  );
  useReconnectRefresh(read, { readAt: () => landedAt.current });

  return minutes;
}
