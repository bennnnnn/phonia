import { isAbortError } from "@/lib/api/abort";
import { request } from "@/lib/api/client";
import i18n from "@/lib/i18n";
import { readRecordingBase64, speechUploadFromUri } from "@/lib/speech/voiceAudio";

function speechLanguageHint(): string | undefined {
  const language = (i18n.resolvedLanguage || i18n.language || "").trim().toLowerCase();
  if (!language) return undefined;
  return language.split("-")[0] || undefined;
}

export async function transcribeSpeech(
  token: string,
  fileUri: string,
  signal?: AbortSignal,
): Promise<string> {
  const upload = speechUploadFromUri(fileUri);
  const audioBase64 = await readRecordingBase64(fileUri);
  if (!audioBase64) {
    throw new Error("recording_empty");
  }
  try {
    const data = await request<{ text?: string }>(
      "/speech/transcribe",
      token,
      {
        method: "POST",
        signal,
        body: JSON.stringify({
          audio_base64: audioBase64,
          filename: upload.name,
          language: speechLanguageHint(),
        }),
      },
      true,
      25_000,
    );
    const text = (data.text ?? "").trim();
    if (!text) throw new Error("transcribe_empty");
    return text;
  } catch (error) {
    if (isAbortError(error)) {
      throw new Error("Transcription timed out. Check your connection.");
    }
    throw error;
  }
}