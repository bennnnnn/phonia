/**
 * Which cloud TTS alias to send to POST /speech/tts. Not a secret — filesystem.
 */
import { prefFilePath, readPrefFile, writePrefFile } from "@/lib/filePrefs";

export const TTS_DEVICE_MODEL = "device";
export const TTS_QUALITY_MODEL = "speech-tts-model";
export const TTS_FAST_MODEL = "speech-tts-fast-model";
type TtsModelAlias =
  | typeof TTS_DEVICE_MODEL
  | typeof TTS_QUALITY_MODEL
  | typeof TTS_FAST_MODEL;

const FILE_NAME = "recall.tts-model.txt";

let cachedPreference: TtsModelAlias | null = null;

export function normalizeTtsModel(raw: string | null | undefined): TtsModelAlias {
  if (raw === TTS_DEVICE_MODEL) return TTS_DEVICE_MODEL;
  return TTS_QUALITY_MODEL;
}

export async function getTtsModel(): Promise<TtsModelAlias> {
  if (cachedPreference !== null) return cachedPreference;
  cachedPreference = normalizeTtsModel(await readPrefFile(prefFilePath(FILE_NAME)));
  return cachedPreference;
}

export async function setTtsModel(model: TtsModelAlias): Promise<void> {
  cachedPreference = model;
  await writePrefFile(prefFilePath(FILE_NAME), model);
}

/** Test helper — reset in-memory cache between cases. */
export function resetTtsModelCache(): void {
  cachedPreference = null;
}
