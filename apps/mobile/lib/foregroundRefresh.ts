import { useEffect, useRef } from "react";
import { AppState, type AppStateStatus } from "react-native";

import { CONTEXT_REFRESH_STALE_MS } from "@/lib/cache/contextRefresh";

/**
 * What the app reads again when it comes back to the foreground, and how old each
 * may be before it is. Six AppState listeners each kept a rule of their own, and a
 * return after a few minutes sent six to nine requests (code-health audit NET-16):
 * the rules are this one table, and the listeners share one native subscription.
 */
export const FOREGROUND_STALE_MS = {
  /** The open chat's newest messages (a turn left running reloads at once). */
  chatMessages: CONTEXT_REFRESH_STALE_MS,
  todos: CONTEXT_REFRESH_STALE_MS,
  usage: CONTEXT_REFRESH_STALE_MS,
  models: 5 * 60_000,
  /** The device's push token at the server. */
  pushRegistration: 12 * 60 * 60_000,
  /** The connection check runs on every return: it clears a stale "No internet". */
  connectivity: 0,
} as const;

/** `returned`: this "active" ends a stay in the background (see `dispatch`). */
type Listener = (state: AppStateStatus, returned: boolean) => void;

const listeners = new Set<Listener>();
let subscription: { remove: () => void } | null = null;
/** The app went to the background since it was last active. */
let away = false;

/**
 * iOS turns "inactive" and back for Control Centre, Notification Centre, a system
 * prompt, Face ID or a call, and the app never leaves the screen: each of those
 * blips used to read the to-dos, the open chat, the models and /health again
 * (three or four requests). Only an "active" after "background" is a return.
 */
function dispatch(state: AppStateStatus): void {
  const returned = state === "active" && away;
  if (state === "background") away = true;
  else if (state === "active") away = false;
  for (const listener of [...listeners]) listener(state, returned);
}

/** Every AppState change, through the one native subscription. */
export function onAppStateChange(listener: Listener): () => void {
  listeners.add(listener);
  if (!subscription) {
    // Launched in the background (a push, a background task): the first "active" is a return.
    away = AppState.currentState === "background";
    subscription = AppState.addEventListener("change", dispatch);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      subscription?.remove();
      subscription = null;
    }
  };
}

/** `refresh` (the latest one) each time the app comes back from the background. */
export function useOnForeground(refresh: () => void, enabled = true): void {
  const latest = useRef(refresh);
  latest.current = refresh;
  useEffect(() => {
    if (!enabled) return;
    return onAppStateChange((_state, returned) => {
      if (returned) latest.current();
    });
  }, [enabled]);
}
