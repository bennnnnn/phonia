/**
 * The native splash stays up until the first screen can be drawn finished:
 * the session restored (or known to be signed out), the fonts in, and the
 * user's appearance and language applied. Never much longer than
 * SPLASH_MAX_MS: a launch that has to wait on the network shows its own
 * loading state rather than a frozen splash.
 *
 * That deadline is the one clock for the launch. When it passes, the root
 * layout stops waiting for fonts and draws (`subscribeLaunchDeadline`), and
 * the splash goes as soon as that tree is committed, so it never uncovers a
 * blank frame.
 */
import * as SplashScreen from "expo-splash-screen";

import { createListenerSet } from "@/lib/listenerSet";

export const SPLASH_MAX_MS = 1_000;
/** If the app never draws at all (a crash before it), the splash still goes. */
const SPLASH_BACKSTOP_MS = 2_000;

type LaunchPart = "session" | "fonts" | "prefs";
const LAUNCH_PARTS: readonly LaunchPart[] = ["session", "fonts", "prefs"];

const ready = new Set<LaunchPart>();
let hidden = false;
let deadlinePassed = false;
const deadline = createListenerSet();

function hideSplash(): void {
  if (hidden) return;
  hidden = true;
  clearTimeout(cap);
  clearTimeout(backstop);
  SplashScreen.hide();
}

/** One frame for the commit that made the first screen ready (and the layout it starts). */
function hideAfterThisFrame(): void {
  requestAnimationFrame(hideSplash);
}

function passDeadline(): void {
  deadlinePassed = true;
  deadline.emit();
  // Whatever else is missing shows its own state (the sign-in spinner, the
  // default theme). The fonts gate decides what is drawn: hide once it is open.
  if (ready.has("fonts")) hideAfterThisFrame();
}

// expo-splash-screen asks for this in global scope, before anything renders.
SplashScreen.preventAutoHideAsync().catch(() => {});
const cap = setTimeout(passDeadline, SPLASH_MAX_MS);
const backstop = setTimeout(hideSplash, SPLASH_BACKSTOP_MS);

/** True once the launch has waited as long as it may. */
export function launchDeadlinePassed(): boolean {
  return deadlinePassed;
}

/** Told once, when the launch has waited as long as it may. */
export function subscribeLaunchDeadline(listener: () => void): () => void {
  return deadline.subscribe(listener);
}

/** One part of the first screen is ready; the last one hides the splash. */
export function markLaunchReady(part: LaunchPart): void {
  if (hidden) return;
  ready.add(part);
  const drawn = deadlinePassed
    ? ready.has("fonts")
    : LAUNCH_PARTS.every((each) => ready.has(each));
  if (drawn) hideAfterThisFrame();
}
