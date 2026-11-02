import { useCallback, useRef, useState } from "react";
import { useFocusEffect } from "expo-router";
import { getSessionGeneration } from "@/lib/auth";
import { useAuth } from "@/contexts/AuthContext";

type ViewOwner = { session: number; visit: number; signedIn: boolean };

/** Dialogs and screen callbacks belong to one focused account visit. */
export function useAccountViewOwner() {
  // Subscribe here: context changes can rerender a child without its wrapper.
  const { token } = useAuth();
  const signedIn = Boolean(token);
  const session = getSessionGeneration();
  const visit = useRef(0);
  const active = useRef<ViewOwner | null>(null);
  const [owner, setOwner] = useState<ViewOwner | null>(null);
  useFocusEffect(useCallback(() => {
    const next = { session, signedIn, visit: ++visit.current };
    active.current = next;
    setOwner(next);
    return () => {
      if (active.current === next) {
        active.current = null;
        setOwner(null);
      }
    };
  }, [session, signedIn]));
  const isCurrent = useCallback(() => owner !== null && owner.signedIn && active.current === owner &&
    owner.session === getSessionGeneration(), [owner]);
  return { key: `${session}:${signedIn}:${owner?.visit ?? 0}`, isCurrent };
}
