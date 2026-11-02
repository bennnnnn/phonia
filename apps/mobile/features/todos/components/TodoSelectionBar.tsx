import { useMemo } from "react";
import { Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

import { makeTodosStyles } from "@/features/todos/components/todosStyles";
import { shadowRaised } from "@/lib/shadow";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";

export function TodoSelectionBar({
  count,
  onComplete,
  onDelete,
}: {
  count: number;
  onComplete: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const C = useTheme();
  const insets = useSafeAreaInsets();
  const s = useMemo(() => makeTodosStyles(C), [C]);
  const ready = count > 0;

  return (
    <View style={[s.selectionBar, shadowRaised(C), { bottom: Math.max(insets.bottom, Space.sm) }]}>
      <Text style={s.selectionCount}>{t("todos.selection_count", { count })}</Text>
      <Pressable
        onPress={onComplete}
        disabled={!ready}
        accessibilityRole="button"
        accessibilityState={{ disabled: !ready }}
        accessibilityLabel={t("todos.selection_complete")}
      >
        <Text style={[s.selectionAction, !ready && s.selectionDisabled]}>
          {t("todos.selection_complete")}
        </Text>
      </Pressable>
      <Pressable
        onPress={onDelete}
        disabled={!ready}
        accessibilityRole="button"
        accessibilityState={{ disabled: !ready }}
        accessibilityLabel={t("common.delete")}
      >
        <Text style={[s.selectionDelete, !ready && s.selectionDisabled]}>
          {t("common.delete")}
        </Text>
      </Pressable>
    </View>
  );
}
