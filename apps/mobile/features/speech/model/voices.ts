import type { UserVoice } from "@/lib/api";

/** Settings → Voice choices, in the order the menu lists them. Names are not translated. */
export const USER_VOICES: readonly UserVoice[] = [
  "marin",
  "cedar",
  "alloy",
  "ash",
  "ballad",
  "coral",
  "echo",
  "sage",
  "shimmer",
  "verse",
];

export function voiceLabel(voice: UserVoice): string {
  return voice.charAt(0).toUpperCase() + voice.slice(1);
}
