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
