import { refreshPhoneClock } from "@/lib/datetime/format";
import { onPhoneClockChange } from "@/lib/datetime/phoneClock";
import { onAppStateChange } from "@/lib/foregroundRefresh";

/**
 * Reads the phone's zone and 12/24-hour setting again when the app comes back from
 * the background (where both are changed) and when the OS reports a change. Kept out
 * of `format.ts`, which stays free of React Native for Node tests.
 */
export function watchPhoneClock(): () => void {
  const stopForeground = onAppStateChange((_state, returned) => {
    if (returned) refreshPhoneClock();
  });
  const stopNative = onPhoneClockChange(refreshPhoneClock);
  return () => {
    stopForeground();
    stopNative();
  };
}
