import { useFonts } from "expo-font";
import { useEffect, useState } from "react";

import { APP_FONT_FACES } from "@/lib/appFonts";
import {
  launchDeadlinePassed,
  markLaunchReady,
  subscribeLaunchDeadline,
} from "@/lib/launchSplash";

/**
 * The faces the app draws with (`lib/appFonts.ts`). True once they are in, or
 * failed, or slower than the launch may wait (a dev server): text laid out
 * before its font is registered keeps the system face, so the root layout
 * draws the app only after this.
 */
export function useLaunchFonts(): boolean {
  // Faces already embedded (every one, in an Android build) load nothing.
  const [loaded, error] = useFonts(APP_FONT_FACES);
  const fontsIn = loaded || error !== null;
  const [gaveUp, setGaveUp] = useState(launchDeadlinePassed);
  // Listened for only while waiting: fonts already in never re-render the app for it.
  useEffect(() => {
    if (fontsIn || gaveUp) return;
    const unsubscribe = subscribeLaunchDeadline(() => setGaveUp(true));
    if (launchDeadlinePassed()) setGaveUp(true);
    return unsubscribe;
  }, [fontsIn, gaveUp]);
  const ready = fontsIn || gaveUp;
  useEffect(() => {
    if (ready) markLaunchReady("fonts");
  }, [ready]);
  return ready;
}
