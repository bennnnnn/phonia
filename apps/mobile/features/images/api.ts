import { request } from "@/lib/api/client";
import type { Message } from "@/lib/api/types";

type ImageGenerateResult = {
  user_message: Message;
  assistant_message: Message;
};

/** A composer send, before it is sent; `chat_id` is null for a draft chat with no turns. */
type ImageIntentRequest = {
  text: string;
  chat_id: string | null;
  image_attached: boolean;
};

/**
 * The server's reading of a send (POST /images/intent), the one the chat turn
 * makes too. `generate_prompt` set: draw it from the composer, from the attached
 * image or `reference_attachment_ids`. Unset: an ordinary chat send.
 */
type ImageIntentVerdict = {
  subject: "math" | "physics" | "chemistry" | null;
  lookup_query: string | null;
  generate_prompt: string | null;
  revision: boolean;
  reference_attachment_ids: string[];
};

/** A slow answer must not hold the composer: the send goes to chat instead. */
const IMAGE_INTENT_TIMEOUT_MS = 3_000;

export const imagesApi = {
  generateImage: (
    token: string,
    body: {
      chat_id: string;
      prompt: string;
      user_message?: string | null;
      aspect_ratio?: string | null;
      reference_attachment_ids?: string[];
    },
    init?: RequestInit,
  ) =>
    request<ImageGenerateResult>(
      "/images/generate",
      token,
      {
        method: "POST",
        body: JSON.stringify(body),
        ...init,
      },
      true,
      120_000,
    ),
  imageIntent: (token: string, body: ImageIntentRequest, init?: RequestInit) =>
    request<ImageIntentVerdict>(
      "/images/intent",
      token,
      {
        method: "POST",
        body: JSON.stringify(body),
        ...init,
      },
      true,
      IMAGE_INTENT_TIMEOUT_MS,
    ),
};
