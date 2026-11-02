/**
 * Sizes for marks that are drawings, not reading text.
 * Keep these out of Type so a display-role change does not resize a glyph.
 */
import type { TextStyle } from "react-native";

export const Graphic = {
  /** Sparkle inside the 72pt onboarding badge. */
  badgeMark: {
    fontSize: 36,
    lineHeight: 40,
  },
} as const satisfies Record<string, TextStyle>;
