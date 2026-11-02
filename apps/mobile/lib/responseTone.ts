const RESPONSE_TONES = ["funny", "professional", "casual", "soft"] as const;

type ResponseTone = (typeof RESPONSE_TONES)[number];

/** Display order in Settings: Natural, Friendly, Professional, Playful. */
export const RESPONSE_TONE_ORDER: ResponseTone[] = ["soft", "casual", "professional", "funny"];

export const DEFAULT_RESPONSE_TONE: ResponseTone = "casual";

export function normalizeResponseTone(value: string | null | undefined): ResponseTone {
  if (value && (RESPONSE_TONES as readonly string[]).includes(value)) {
    return value as ResponseTone;
  }
  return DEFAULT_RESPONSE_TONE;
}

const EMOJI_USES = ["off", "some", "more"] as const;

type EmojiUse = (typeof EMOJI_USES)[number];

/** Settings order: None, A few, Lots. Every account starts at a few. */
export const EMOJI_USE_ORDER: readonly EmojiUse[] = EMOJI_USES;

const DEFAULT_EMOJI_USE: EmojiUse = "some";

export function normalizeEmojiUse(value: string | null | undefined): EmojiUse {
  if (value && (EMOJI_USES as readonly string[]).includes(value)) {
    return value as EmojiUse;
  }
  return DEFAULT_EMOJI_USE;
}
