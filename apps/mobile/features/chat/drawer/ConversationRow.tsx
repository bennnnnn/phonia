import { memo } from "react";
import { Pressable, StyleSheet, Text, View, ViewStyle, TextStyle } from "react-native";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { Theme, useTheme } from "@/lib/theme";
import { Italic, Type, Weight } from "@/lib/type";
import type { Chat } from "@/lib/api";
import { displayChatTitle } from "@/features/chat/model/title";
import { IconSize } from "@/ui/icons/sizes";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";

type ConversationRowStyles = {
  row: ViewStyle;
  rowIcon: ViewStyle;
  title: TextStyle;
  titlePending: TextStyle;
  titleActive: TextStyle;
  rowHighlighted: ViewStyle;
  rowActive: ViewStyle;
  rowSelected: ViewStyle;
  rowPressed: ViewStyle;
};

type Props = {
  chat: Chat;
  /**
   * Stable callbacks (e.g. the useCallback-wrapped onOpenChat/onShowRowMenu
   * from the parent), not a per-row closure — this row is memoized, and a
   * fresh `() => onOpen(chatId)` created on every renderItem call would
   * defeat that by changing the onOpen prop's identity every render.
   */
  onOpen: (chatId: string) => void;
  /** `point` is where the finger was, so the row menu opens there. */
  onLongPress: (chat: Chat, point: { x: number; y: number }) => void;
  selectionMode?: boolean;
  selected?: boolean;
  onToggleSelect?: (chatId: string) => void;
  highlighted?: boolean;
  /** Currently open chat on the home screen. */
  active?: boolean;
  titleGenerating?: boolean;
  rowStyles: ConversationRowStyles;
};

export const ConversationRow = memo(function ConversationRow({
  chat,
  onOpen,
  onLongPress,
  selectionMode = false,
  selected = false,
  onToggleSelect,
  highlighted = false,
  active = false,
  titleGenerating = false,
  rowStyles: r,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const label = displayChatTitle(chat.title, { generating: titleGenerating }, t);

  return (
    <Pressable
      style={({ pressed }) => [
        r.row,
        highlighted && r.rowHighlighted,
        active && !selectionMode && r.rowActive,
        selected && r.rowSelected,
        pressed && r.rowPressed,
      ]}
      onPress={() => {
        if (selectionMode) onToggleSelect?.(chat.id);
        else onOpen(chat.id);
      }}
      onLongPress={(event) => {
        if (selectionMode) onToggleSelect?.(chat.id);
        else onLongPress(chat, { x: event.nativeEvent.pageX, y: event.nativeEvent.pageY });
      }}
      accessibilityRole={selectionMode ? "checkbox" : "button"}
      accessibilityLabel={label}
      accessibilityState={
        selectionMode ? { checked: selected } : { selected: active }
      }
    >
      {selectionMode ? (
        <View style={r.rowIcon}>
          <Icon
            name={selected ? "checkbox-checked" : "square"}
            size={IconSize.sm}
            color={selected ? theme.primary : theme.textTertiary}
          />
        </View>
      ) : chat.pinned ? (
        <View style={r.rowIcon}>
          <Icon name="bookmark" size={IconSize.xs} color={theme.primary} />
        </View>
      ) : null}
      <Text
        style={[
          r.title,
          titleGenerating && !chat.title && r.titlePending,
          active && !selectionMode && r.titleActive,
        ]}
        numberOfLines={1}
      >
        {label}
      </Text>
    </Pressable>
  );
});

export function makeConversationRowStyles(theme: Theme): ConversationRowStyles {
  return StyleSheet.create({
    row: {
      flexDirection: "row",
      alignItems: "center",
      minHeight: 44,
      paddingVertical: Space.sm,
      paddingHorizontal: Space.md,
      gap: Space.sm,
    },
    rowIcon: { flexShrink: 0 },
    title: { flex: 1, ...Type.body, ...Weight.medium, color: theme.text },
    titlePending: { color: theme.textTertiary, ...Italic.regular },
    // Wash already signals active — keep ink on theme.text, just bolder.
    titleActive: { ...Weight.bold },
    rowHighlighted: {
      backgroundColor: theme.primaryLight,
      borderRadius: Radius.sm,
      marginHorizontal: Space.xs,
      paddingHorizontal: Space.xs,
    },
    rowActive: {
      backgroundColor: theme.surfaceAlt,
      borderRadius: Radius.sm,
      marginHorizontal: Space.xs,
      paddingHorizontal: Space.xs,
    },
    rowSelected: {
      backgroundColor: theme.primaryLight,
    },
    rowPressed: { opacity: 0.72 },
  });
}
