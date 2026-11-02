/**
 * Settings → Voice → Speed: how fast read-aloud plays, on this device.
 * Live talk speaks at its own pace. Not a secret — a file.
 */
import { prefFilePath, readPrefFile, writePrefFile } from "@/lib/filePrefs";

export const SPEECH_RATES = [0.75, 1, 1.25, 1.5] as const;
export type SpeechRate = (typeof SPEECH_RATES)[number];

const FILE_NAME = "recall.speech-rate.txt";

let cachedRate: SpeechRate | null = null;

export function normalizeSpeechRate(raw: string | number | null | undefined): SpeechRate {
  const value = typeof raw === "number" ? raw : Number.parseFloat(raw ?? "");
  return SPEECH_RATES.find((rate) => rate === value) ?? 1;
}

export async function getSpeechRate(): Promise<SpeechRate> {
  if (cachedRate !== null) return cachedRate;
  cachedRate = normalizeSpeechRate(await readPrefFile(prefFilePath(FILE_NAME)));
  return cachedRate;
}

/** The loaded rate; 1 until getSpeechRate has read the file once. */
export function currentSpeechRate(): SpeechRate {
  return cachedRate ?? 1;
}

export async function setSpeechRate(rate: SpeechRate): Promise<void> {
  cachedRate = rate;
  await writePrefFile(prefFilePath(FILE_NAME), String(rate));
}

/** Test helper — reset in-memory cache between cases. */
export function resetSpeechRateCache(): void {
  cachedRate = null;
}
