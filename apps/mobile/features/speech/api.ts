import { isAbortError } from "@/lib/api/abort";
import { request } from "@/lib/api/client";
import i18n from "@/lib/i18n";
import { readRecordingBase64, speechUploadFromUri } from "@/lib/speech/voiceAudio";
import type { LiveTalkStatus } from "@/features/speech/model/liveTalkLogic";
import type { Message, SearchSource } from "@/lib/api/types";

type RealtimeSessionCredential = {
  client_secret: string;
  expires_at: number;
  call_id: string;
  model: string;
  /** Seconds reserved from this month's live talk minutes; hang up here. */
  max_duration_seconds?: number;
};

export const speechApi = {
  liveTalkStatus: (token: string) => request<LiveTalkStatus>("/speech/live", token),
  createRealtimeSession: (token: string, body: { chatId?: string | null; bargeIn?: boolean }) =>
    request<RealtimeSessionCredential>(
      "/speech/live/session",
      token,
      {
        method: "POST",
        body: JSON.stringify({
          ...(body.chatId ? { chat_id: body.chatId } : {}),
          barge_in: body.bargeIn ?? false,
          tools_enabled: Boolean(body.chatId),
        }),
      },
      true,
      15_000,
    ),
  persistRealtimeLiveTalkTurn: (
    token: string,
    body: { chatId: string; callId: string; userText: string; assistantText: string; turnId?: string },
  ) =>
    request<{ user_message: Message | null; assistant_message: Message | null } | undefined>("/speech/live/persist", token, {
      method: "POST",
      body: JSON.stringify({
        chat_id: body.chatId,
        call_id: body.callId,
        user_text: body.userText,
        assistant_text: body.assistantText,
        turn_id: body.turnId,
        return_messages: true,
      }),
    }),
  /** Hung up: the server charges the time used and gives the rest back. */
  endRealtimeSession: (token: string, callId: string) =>
    request<LiveTalkStatus>("/speech/live/end", token, {
      method: "POST",
      body: JSON.stringify({ call_id: callId }),
    }),
  realtimeTool: (token: string, body: {
    chat_id: string; call_id: string; turn_id: string;
    name: "memory_lookup" | "web_search"; query: string;
  }) => request<{ content: string; sources?: SearchSource[] }>("/speech/live/tool", token, {
    method: "POST", body: JSON.stringify(body),
  }, true, 15_000),
};

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