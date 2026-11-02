import { useMemo, useState } from "react";
import { Keyboard, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { TodoPickerSheet } from "@/features/todos/components/TodoPickerSheet";
import { makeTodosStyles } from "@/features/todos/components/todosStyles";
import {
  BUILTIN_CATEGORIES,
  categoryText,
  isBuiltinCategory,
  isNoCategory,
  resolveCategoryName,
} from "@/features/todos/model/todoCategories";
import { DEFAULT_TOPIC } from "@/features/todos/model/todoTopics";
import type { Todo } from "@/lib/api";
import { IconSize } from "@/ui/icons/sizes";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

function choices(
  todos: Todo[],
  topic: string,
  t: (key: string) => string,
): { key: string; label: string }[] {
  const custom = new Set<string>();
  for (const todo of todos) {
    const name = todo.topic?.trim();
    if (!name || isNoCategory(name) || isBuiltinCategory(name)) continue;
    custom.add(name);
  }
  if (!isNoCategory(topic) && !isBuiltinCategory(topic)) custom.add(topic);
  return [
    { key: DEFAULT_TOPIC, label: t("todos.category_none") },
    ...BUILTIN_CATEGORIES.map((id) => ({ key: id, label: t(`todos.category_${id}`) })),
    ...[...custom].sort((a, b) => a.localeCompare(b)).map((name) => ({ key: name, label: name })),
  ];
}

export function TodoCategoryField({
  topic,
  disabled,
  review = false,
  onOpen,
}: {
  topic: string;
  disabled?: boolean;
  /** Chip on the detail page, instead of a labeled form field. */
  review?: boolean;
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  const C = useTheme();
  const s = useMemo(() => makeTodosStyles(C), [C]);
  const current = categoryText(topic, t) ?? t("todos.category_none");
  const open = () => {
    Keyboard.dismiss();
    onOpen();
  };

  if (review) {
    return (
      <Pressable
        style={s.reviewChip}
        onPress={open}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityLabel={`${t("todos.category_label")}, ${current}`}
      >
        <Text style={s.reviewChipText}>{current}</Text>
        {disabled ? null : <Icon name="chevron-down" size={IconSize.sm} color={C.textTertiary} />}
      </Pressable>
    );
  }

  return (
    <View>
      <Text style={s.formLabel}>{t("todos.category_label")}</Text>
      <Pressable
        style={s.repeatField}
        onPress={open}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityLabel={`${t("todos.category_label")}, ${current}`}
      >
        <Text style={s.repeatFieldText}>{current}</Text>
        <Icon name="chevron-right" size={IconSize.sm} color={C.textTertiary} />
      </Pressable>
    </View>
  );
}

export function TodoCategoryPicker({
  topic,
  todos,
  disabled,
  onChange,
  onClose,
}: {
  topic: string;
  todos: Todo[];
  disabled?: boolean;
  onChange: (topic: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const C = useTheme();
  const s = useMemo(() => makePickerStyles(C), [C]);
  const [draft, setDraft] = useState("");
  const [creating, setCreating] = useState(false);
  const options = useMemo(() => choices(todos, topic, t), [todos, topic, t]);

  const close = () => {
    setCreating(false);
    setDraft("");
    onClose();
  };

  const create = () => {
    const next = resolveCategoryName(draft);
    if (!next) return;
    onChange(next);
    close();
  };

  return (
    <TodoPickerSheet
      visible
      options={options}
      selectedKey={topic}
      disabled={disabled}
      keyboardAvoiding={creating}
      onSelect={onChange}
      onClose={close}
      footer={
        creating ? (
          <TextInput
            style={s.input}
            value={draft}
            onChangeText={setDraft}
            placeholder={t("todos.category_placeholder")}
            placeholderTextColor={C.textDisabled}
            autoFocus
            editable={!disabled}
            maxLength={200}
            returnKeyType="done"
            onSubmitEditing={create}
            accessibilityLabel={t("todos.category_placeholder")}
          />
        ) : (
          <Pressable
            style={s.create}
            onPress={() => setCreating(true)}
            disabled={disabled}
            accessibilityRole="button"
            accessibilityLabel={t("todos.category_new")}
          >
            <Icon name="plus" size={IconSize.md} color={C.primary} />
            <Text style={s.createLabel}>{t("todos.category_new")}</Text>
          </Pressable>
        )
      }
    />
  );
}

function makePickerStyles(theme: Theme) {
  return StyleSheet.create({
    create: {
      flex: 1,
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
    },
    createLabel: { ...Type.body, color: theme.primary },
    input: { flex: 1, ...Type.body, color: theme.text },
  });
}
