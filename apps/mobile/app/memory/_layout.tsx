import { Stack } from "expo-router";
import { useTranslation } from "react-i18next";

import { stackBackOptions } from "@/ui/controls/StackBackButton";
import { nestedStackScreenOptions, useStackHeaderOptions } from "@/lib/stackHeader";
import { useReduceMotion } from "@/lib/reduceMotion";
import { useTheme } from "@/lib/theme";

/** A crash on any page of this stack shows the shared error view here, not the whole app's. */
export { ScreenErrorBoundary as ErrorBoundary } from "@/components/ScreenErrorBoundary";

export default function MemoryLayout() {
  const { t } = useTranslation();
  const theme = useTheme();
  const header = useStackHeaderOptions();
  const reduceMotion = useReduceMotion();

  return (
    <Stack
      screenOptions={{
        ...nestedStackScreenOptions(theme, header, reduceMotion),
        title: t("memory.title"),
      }}
    >
      <Stack.Screen name="index" options={stackBackOptions()} />
      <Stack.Screen name="[key]" options={stackBackOptions("/memory")} />
    </Stack>
  );
}
