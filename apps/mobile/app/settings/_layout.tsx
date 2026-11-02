import { Stack } from "expo-router";
import { useTranslation } from "react-i18next";

import { stackBackOptions } from "@/ui/controls/StackBackButton";
import {
  nestedStackScreenOptions,
  type StackHeaderOptions,
  useStackHeaderOptions,
} from "@/lib/stackHeader";
import { useReduceMotion } from "@/lib/reduceMotion";
import { useTheme } from "@/lib/theme";

/** A crash on any page of this stack shows the shared error view here, not the whole app's. */
export { ScreenErrorBoundary as ErrorBoundary } from "@/components/ScreenErrorBoundary";

/**
 * Every Settings sub-page, in order: its route file in `app/settings/` and its
 * header title. A new page is its route file plus one row here.
 */
const SETTINGS_PAGES = [
  { name: "profile", title: "settings.profile" },
  { name: "usage", title: "settings.usage_group" },
  { name: "models", title: "settings.model" },
  { name: "voice", title: "settings.voice" },
  { name: "preferences", title: "settings.personalization" },
  { name: "memory-settings", title: "settings.memory" },
  { name: "notifications", title: "settings.notifications" },
  { name: "data-controls", title: "settings.data_controls" },
  { name: "archived-chats", title: "settings.archived_chats" },
  { name: "security", title: "settings.security" },
  { name: "about", title: "settings.about" },
  { name: "help", title: "settings.help" },
  { name: "licenses", title: "settings.licenses" },
] as const;

function subScreen(title: string, header: StackHeaderOptions) {
  return {
    ...header,
    title,
    ...stackBackOptions("/settings"),
  };
}

export default function SettingsLayout() {
  const { t } = useTranslation();
  const theme = useTheme();
  const header = useStackHeaderOptions();
  const reduceMotion = useReduceMotion();

  return (
    <Stack
      screenOptions={{
        ...nestedStackScreenOptions(theme, header, reduceMotion),
        ...stackBackOptions("/"),
      }}
    >
      <Stack.Screen name="index" options={{ title: t("settings.title"), headerShown: false }} />
      {SETTINGS_PAGES.map((page) => (
        <Stack.Screen key={page.name} name={page.name} options={subScreen(t(page.title), header)} />
      ))}
    </Stack>
  );
}
