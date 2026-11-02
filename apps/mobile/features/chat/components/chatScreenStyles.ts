import { StyleSheet } from "react-native";

import { Radius } from "@/lib/radius";
import { shadowRaised } from "@/lib/shadow";
import { Space } from "@/lib/space";
import type { Theme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

export function makeChatScreenStyles(C: Theme) {
  return StyleSheet.create({
    container: { flex: 1, backgroundColor: C.bg },
    quotaNudge: {
      position: "absolute",
      left: Space.xs,
      right: Space.xs,
      flexDirection: "row",
      alignItems: "center",
      backgroundColor: C.surfaceAlt,
      borderRadius: Radius.md,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.xs,
      gap: Space.xs,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: C.border,
      ...shadowRaised(C),
    },
    quotaNudgeBody: {
      flex: 1,
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
    },
    quotaNudgeIcon: { flexShrink: 0 },
    quotaNudgeText: {
      flex: 1,
      ...Type.caption,
      ...Weight.regular,
      color: C.text,
    },
    quotaNudgeCta: {
      backgroundColor: C.primary,
      borderRadius: Radius.xs,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.xxs,
      flexShrink: 0,
    },
    quotaNudgeCtaText: {
      ...Type.caption,
      ...Weight.bold,
      color: C.onPrimary,
    },
    quotaNudgeClose: { padding: Space.xxs, flexShrink: 0 },
  });
}

export type ChatScreenStyles = ReturnType<typeof makeChatScreenStyles>;
