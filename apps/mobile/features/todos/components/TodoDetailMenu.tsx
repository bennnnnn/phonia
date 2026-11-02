import type { RefObject } from "react";
import type { View } from "react-native";
import { useTranslation } from "react-i18next";

import { Menu } from "@/ui/overlay/Menu";

/** To-do detail ⋮: mark done (or open again), or delete. */
export function TodoDetailMenu({
  visible,
  checked,
  anchorRef,
  onMarkDone,
  onDelete,
  onClose,
}: {
  visible: boolean;
  checked: boolean;
  anchorRef: RefObject<View | null>;
  onMarkDone: () => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();

  return (
    <Menu
      visible={visible}
      onClose={onClose}
      anchorRef={anchorRef}
      testID="todo-detail-menu"
      items={[
        {
          key: "done",
          icon: checked ? "circle" : "check-circle",
          label: checked ? t("todos.mark_open") : t("todos.selection_complete"),
          onPress: onMarkDone,
        },
        {
          key: "delete",
          icon: "trash",
          label: t("common.delete"),
          onPress: onDelete,
          destructive: true,
        },
      ]}
    />
  );
}
