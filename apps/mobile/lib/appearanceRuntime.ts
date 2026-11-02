import type { AppearancePreference } from "@/lib/appearance";
import { createValueStore } from "@/lib/listenerSet";

const preference = createValueStore<AppearancePreference>("system");

export function getAppearancePreferenceSnapshot(): AppearancePreference {
  return preference.get();
}

export function setAppearancePreferenceSnapshot(next: AppearancePreference): void {
  preference.set(next);
}

export function subscribeAppearancePreference(listener: () => void): () => void {
  return preference.subscribe(listener);
}

/** Test helper — reset store between cases. */
export function resetAppearanceRuntime(): void {
  preference.reset();
}
