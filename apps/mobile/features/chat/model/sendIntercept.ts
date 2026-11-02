import type { Message } from "@/lib/api";
import type { PendingAttachment } from "@/features/attachments/model/attachments";
import { readImageTurn } from "@/features/images/model/imageGenTurn";
import { mightBeImageTurn } from "@/features/images/model/imageIntentPrefilter";

type ImageReference = { attachment?: PendingAttachment; ids?: string[] };

export type SendIntercept =
  /** A reference photo: the backend's image_search attaches it to an ordinary reply. */
  | { kind: "lookup" }
  | { kind: "send" }
  | { kind: "generate"; prompt: string; reference?: ImageReference }
  /** An image is still generating, so the tap is dropped. */
  | { kind: "drop" }
  /** The user left the view while the server was asked. */
  | { kind: "stale" };

type InterceptInput = {
  text: string;
  attachment: PendingAttachment | null;
  /** The chat the send goes to; null for a draft chat with no turns yet. */
  chatId: string | null;
  messages: Message[];
  canGenerate: boolean;
  imageGenerating: boolean;
  token: string | null;
  isCurrentView: () => boolean;
};

/**
 * What the composer makes of a send before chat sees it: a photo lookup, an image to
 * generate, or a normal send. Only the server reads image intent (POST /images/intent);
 * the phone asks it, after the bubble is painted, when the send might be one. A send
 * that cannot be one stays synchronous and goes out in the tap's own tick.
 */
export function resolveSendIntercept(input: InterceptInput): SendIntercept | Promise<SendIntercept> {
  const { text, attachment, token } = input;
  // Do not gate on client isPaid — plan can be stale while the API still knows Pro;
  // submitPrompt / the API open upgrade or generate. A file attachment is never a
  // picture to draw.
  if (!input.canGenerate || !token || (attachment && attachment.kind !== "image")) return { kind: "send" };
  const imageAttached = attachment?.kind === "image";
  if (!mightBeImageTurn(text, input.messages, imageAttached)) return { kind: "send" };
  return askServer(input, token, imageAttached);
}

async function askServer(
  input: InterceptInput,
  token: string,
  imageAttached: boolean,
): Promise<SendIntercept> {
  const reading = await readImageTurn(token, {
    text: input.text,
    chatId: input.chatId,
    imageAttached,
  });
  if (!input.isCurrentView()) return { kind: "stale" };
  if (reading.kind !== "generate") return reading;
  if (input.imageGenerating) return { kind: "drop" };
  const reference = input.attachment ? { attachment: input.attachment }
    : reading.referenceIds.length ? { ids: reading.referenceIds } : undefined;
  return { kind: "generate", prompt: reading.prompt, reference };
}
