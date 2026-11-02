import { StyleSheet } from "react-native";
import { useTranslation } from "react-i18next";

import { tap } from "@/lib/haptics";
import { Space } from "@/lib/space";
import { Button } from "@/ui/controls/Button";

/** The router loads on the tap: every reply bubble draws this file, few press it. */
async function openTodos(): Promise<void> {
  const { router } = await import("expo-router");
  router.push("/todos");
}

/**
 * Under a reply that asked to add or change a to-do in a language other than
 * English: chat only reads to-dos there, so the change is made in To-do.
 */
export function TodoLinkButton() {
  const { t } = useTranslation();
  return (
    <Button
      title={t("todos.open_from_chat")}
      icon="calendar"
      variant="secondary"
      size="sm"
      onPress={() => {
        tap();
        void openTodos();
      }}
      style={s.button}
      testID="todo-link-button"
    />
  );
}

const s = StyleSheet.create({
  button: { alignSelf: "flex-start", marginTop: Space.sm },
});
