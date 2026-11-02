import { useCallback } from "react";
import { useFocusEffect } from "expo-router";

import { useLatestRef } from "@/lib/latestRef";
import { onReconnect, readSinceLost } from "@/lib/reconnectRefresh";

type Options = {
  /** Its list is the one showing (the drawer open, the screen's own view current). */
  onScreen?: () => boolean;
  /** When the list last came from the server, by any path: its cache's time, or its own. */
  readAt?: () => number | undefined;
};

/**
 * Reads this screen's list again once the API answers after an outage (lib/reconnectRefresh.ts):
 * `refresh` (the latest) runs once, a random 0–10 s later, while the screen has focus and
 * `onScreen` (the latest), when given, says its list is the one showing. A read that landed
 * since the connection was lost (`readAt`: the screen opened, pulled, or its read cleared the
 * banner) is that read: the list is not read again.
 */
export function useReconnectRefresh(refresh: () => void, { onScreen, readAt }: Options = {}): void {
  const latest = useLatestRef({ refresh, onScreen, readAt });
  useFocusEffect(
    useCallback(
      () => onReconnect(() => {
        if (!readSinceLost(latest.current.readAt?.())) latest.current.refresh();
      }, () => latest.current.onScreen?.() ?? true),
      [latest],
    ),
  );
}
