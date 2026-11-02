import type { RefObject } from "react";
import type { View } from "react-native";
import { useTranslation } from "react-i18next";

import type { TodoView } from "@/features/todos/model/todoListFilter";
import { Menu } from "@/ui/overlay/Menu";

const VIEWS: { id: TodoView; label: string }[] = [
  { id: "all", label: "todos.menu_all" },
  { id: "open", label: "todos.menu_open" },
  { id: "completed", label: "todos.menu_completed" },
  { id: "today", label: "todos.menu_today" },
];

/** To-do list ⋮: start selecting, or switch which to-dos the list shows. */
export function TodosViewMenu({
  visible,
  view,
  anchorRef,
  onView,
  onSelect,
  onClose,
}: {
  visible: boolean;
  view: TodoView;
  anchorRef: RefObject<View | null>;
  onView: (view: TodoView) => void;
  onSelect: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();

  return (
    <Menu
      visible={visible}
      onClose={onClose}
      anchorRef={anchorRef}
      testID="todos-view-menu"
      items={[
        { key: "select", icon: "select", label: t("todos.menu_select"), onPress: onSelect },
        "separator",
        ...VIEWS.map((item) => ({
          key: item.id,
          label: t(item.label),
          selected: item.id === view,
          onPress: () => onView(item.id),
        })),
      ]}
    />
  );
}
