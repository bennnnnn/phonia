import { useCallback, useSyncExternalStore } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { getSessionGeneration } from "@/lib/auth";
import { createListenerSet } from "@/lib/listenerSet";

let pending: { session: number } | null = null;
const listeners = createListenerSet();

/** Keep one account's preference write exclusive even if its settings screen remounts. */
export function useMemoryToggle(isCurrentView: () => boolean, onError: () => void) {
  const { updateUser } = useAuth();
  const session = getSessionGeneration();
  const saving = useSyncExternalStore(listeners.subscribe, () => pending?.session === session);
  const toggle = useCallback((enabled: boolean) => {
    if (!isCurrentView() || session !== getSessionGeneration() || pending?.session === session) return;
    const request = { session };
    pending = request;
    listeners.emit();
    void updateUser({ memory_enabled: enabled })
      .catch(() => { if (isCurrentView() && session === getSessionGeneration()) onError(); })
      .finally(() => {
        if (pending === request) { pending = null; listeners.emit(); }
      });
  }, [isCurrentView, session, updateUser, onError]);
  return { saving, toggle };
}
