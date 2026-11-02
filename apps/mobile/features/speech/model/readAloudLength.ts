import { markdownToSpeechText } from "@/lib/markdown/plain";

/** The longest text /speech/tts accepts (`max_length` in the API's speech schemas). */
export const TTS_MAX_CHARS = 4000;

/**
 * The part of `text` read aloud: all of it, or up to the limit, ending at the last
 * sentence end (else the last space) before it, never in the middle of a word.
 */
export function readAloudPart(text: string): string {
  if (text.length <= TTS_MAX_CHARS) return text.trim();
  const head = text.slice(0, TTS_MAX_CHARS);
  const sentence = Math.max(head.lastIndexOf(". "), head.lastIndexOf("\n"));
  const cut = sentence > TTS_MAX_CHARS / 2 ? sentence + 1 : head.lastIndexOf(" ");
  return (cut > 0 ? head.slice(0, cut) : head).trim();
}

/** Read aloud stops before the end of this reply, so the reader is told. */
export function readAloudIsCut(markdown: string): boolean {
  return markdownToSpeechText(markdown).length > TTS_MAX_CHARS;
}
