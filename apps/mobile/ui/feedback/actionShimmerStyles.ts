import { StyleSheet } from "react-native";

import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import type { Theme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

export const SHIMMER_BAND_WIDTH = 64;

/** One look for the shimmer and the still label it shows until the motion loads. */
export function makeActionShimmerStyles(theme: Theme) {
  return StyleSheet.create({
    wrap: {
      minHeight: 24,
      minWidth: 72,
      alignSelf: "center",
      alignItems: "center",
      justifyContent: "center",
      flexDirection: "row",
      gap: Space.xs,
      overflow: "hidden",
      borderRadius: Radius.sm,
      paddingHorizontal: Space.xs,
    },
    compact: {
      minHeight: 18,
      minWidth: 0,
      paddingHorizontal: 0,
    },
    label: {
      ...Type.label,
      ...Weight.bold,
      color: theme.primary,
    },
    band: {
      position: "absolute",
      top: 0,
      bottom: 0,
      width: SHIMMER_BAND_WIDTH,
    },
    dot: {
      width: 6,
      height: 6,
      borderRadius: Radius.full,
    },
  });
}
