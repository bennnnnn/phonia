import { useMemo } from "react";

import { stackPushTransition } from "@/lib/stackTransitions";
import { type Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

/** Shared stack header options — keeps back chevron and title styling consistent. */
function stackHeaderOptions(theme: Theme) {
  return {
    headerStyle: { backgroundColor: theme.bg },
    headerTitleStyle: {
      ...Type.navTitle,
      color: theme.text,
    },
    headerShadowVisible: false,
    headerTintColor: theme.text,
    headerBackTitle: "",
    headerBackTitleVisible: false,
  } as const;
}

export type StackHeaderOptions = ReturnType<typeof stackHeaderOptions>;

/** `stackHeaderOptions` for the current theme, rebuilt only when the theme changes. */
export function useStackHeaderOptions(): StackHeaderOptions {
  const theme = useTheme();
  return useMemo(() => stackHeaderOptions(theme), [theme]);
}

/**
 * What every nested push stack (Settings, Memory) shows: the push transition,
 * the themed header, and our own back button in place of the native one.
 */
export function nestedStackScreenOptions(
  theme: Theme,
  header: StackHeaderOptions,
  reduceMotion: boolean,
) {
  return {
    ...stackPushTransition(reduceMotion),
    ...header,
    headerShown: true,
    contentStyle: { backgroundColor: theme.bg },
    headerBackVisible: false,
  };
}
