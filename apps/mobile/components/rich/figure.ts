/** Shared frame for the rich figures: graphs and physics scenes. */
import type { TextStyle } from "react-native";

import type { Theme } from "@/lib/theme";
import { Type } from "@/lib/type";

/** Side gutters of a chat message around a figure. */
const FIGURE_GUTTER = 48;
/** Widest a figure grows, so a tablet does not get a billboard. */
const FIGURE_MAX_WIDTH = 360;

export function figureWidth(screenWidth: number): number {
  return Math.min(screenWidth - FIGURE_GUTTER, FIGURE_MAX_WIDTH);
}

/** The one title style for a figure, always set above its canvas. */
export function figureTitleStyle(theme: Theme): TextStyle {
  return {
    ...Type.callout,
    color: theme.text,
    marginBottom: 2,
    textAlign: "center",
  };
}

/** About one line of `figureTitleStyle` plus its margin, for placeholders. */
export const FIGURE_TITLE_HEIGHT = 22;
