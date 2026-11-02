import { api, type Message } from "@/lib/api";
import {
  IMAGE_GEN_FAILED_ASSISTANT_ID,
  IMAGE_GEN_PENDING_ASSISTANT_ID,
} from "@/features/images/model/imageGenMessages";

type ImageGenFailure = "canceled" | "failed";

/** What the server reads a composer send as. A maths, physics or chemistry turn is a send. */
type ImageTurnReading =
  | { kind: "send" }
  /** A real photo: the chat turn looks it up and attaches it to its reply. */
  | { kind: "lookup" }
  /** A picture to draw from the composer; `referenceIds` is the earlier picture an edit starts from. */
  | { kind: "generate"; prompt: string; referenceIds: string[] };

/**
 * The server's reading of a send that might be a picture (POST /images/intent).
 * Any failure (offline, an error, a slow answer) reads as a plain send: the chat
 * turn reads the text again on the server, so a picture request still draws.
 */
export async function readImageTurn(
  token: string,
  send: { text: string; chatId: string | null; imageAttached: boolean },
): Promise<ImageTurnReading> {
  try {
    const verdict = await api.imageIntent(token, {
      text: send.text,
      chat_id: send.chatId,
      image_attached: send.imageAttached,
    });
    if (verdict.generate_prompt) {
      return {
        kind: "generate",
        prompt: verdict.generate_prompt,
        referenceIds: verdict.reference_attachment_ids ?? [],
      };
    }
    return verdict.lookup_query ? { kind: "lookup" } : { kind: "send" };
  } catch {
    return { kind: "send" };
  }
}

/** Show what the user typed — never rewrite to "Generate image: …". */
export function imageGenUserBubble(userMessage: string, prompt: string): string {
  return userMessage.trim() || prompt.trim();
}

/** `refused`: the server will refuse a retry the same way, so the card offers none. */
export function applyImageGenFailure(
  messages: readonly Message[],
  outcome: ImageGenFailure,
  errorText?: string,
  refused = false,
): Message[] {
  return messages.map((row) =>
    row.id === IMAGE_GEN_PENDING_ASSISTANT_ID
      ? {
          ...row,
          id: IMAGE_GEN_FAILED_ASSISTANT_ID,
          content: "",
          image_gen_failure: outcome,
          image_gen_error: errorText,
          image_gen_refused: refused || undefined,
        }
      : row,
  );
}

/**
 * The saved turn in place of the painted one (`optimisticUserId` and the pending picture).
 * Back in its chat, the page read on return may already hold the saved rows: one copy shows.
 */
export function applyImageGenSuccess(
  messages: readonly Message[],
  optimisticUserId: string,
  saved: readonly Message[],
): Message[] {
  const kept = messages.filter((row) => row.id !== optimisticUserId && row.id !== IMAGE_GEN_PENDING_ASSISTANT_ID);
  const shown = new Set(kept.map((row) => row.id));
  return [...kept, ...saved.filter((row) => !shown.has(row.id))];
}

export function restoreImageGenPending(messages: readonly Message[]): Message[] {
  return messages.map((row) =>
    row.id === IMAGE_GEN_FAILED_ASSISTANT_ID
      ? {
          ...row,
          id: IMAGE_GEN_PENDING_ASSISTANT_ID,
          content: "",
          image_gen_failure: undefined,
          image_gen_error: undefined,
          image_gen_refused: undefined,
        }
      : row,
  );
}

export function hasImageGenFailedAssistant(messages: readonly Message[]): boolean {
  return messages.some((row) => row.id === IMAGE_GEN_FAILED_ASSISTANT_ID);
}
