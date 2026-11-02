import { useSyncExternalStore } from "react";

import { DEFAULT_ACCENT, type AccentPreference } from "@/lib/accent";
import { createValueStore } from "@/lib/listenerSet";

const accent = createValueStore<AccentPreference>(DEFAULT_ACCENT);

function getAccentSnapshot(): AccentPreference {
  return accent.get();
}

export function setAccentSnapshot(next: AccentPreference): void {
  accent.set(next);
}

function subscribeAccent(listener: () => void): () => void {
  return accent.subscribe(listener);
}

/** The accent color the user picked (Settings → Accent color). */
export function useAccentPreference(): AccentPreference {
  return useSyncExternalStore(subscribeAccent, getAccentSnapshot, getAccentSnapshot);
}
