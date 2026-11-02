import { memo, useMemo } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { useTranslation } from "react-i18next";

import { MathConverterPad } from "@/features/chat/components/MathConverterPad";
import { MathKey } from "@/features/chat/components/MathKey";
import { selection as hapticSelection } from "@/lib/haptics";
import { PAD_GAP, TAB_ROW_HEIGHT, padKeyHeight } from "@/lib/math/keyboardPad";
import {
  MATH_KEYBOARD_GROUPS,
  padRows,
  symbolA11yLabel,
  type MathKeyboardGroup,
  type MathKeyboardSymbol,
  type PadCell,
  type SymbolPage,
} from "@/lib/math/keyboardSymbols";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Button } from "@/ui/controls/Button";
import { Chip } from "@/ui/controls/Chip";
import { IconButton } from "@/ui/controls/IconButton";
import { IconSize } from "@/ui/icons/sizes";

type Props = {
  open: boolean;
  height: number;
  onToggle: () => void;
  onInsert: (spec: MathKeyboardSymbol) => void;
  onCaret: (direction: "left" | "right") => void;
  onAsk: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
  onBackspace: () => void;
  onPaste: () => void;
  group: MathKeyboardGroup;
  onGroupChange: (group: MathKeyboardGroup) => void;
};

export const MathKeyboardBar = memo(function MathKeyboardBar({
  open,
  height,
  onToggle,
  onInsert,
  onCaret,
  onAsk,
  onStop,
  streaming,
  onBackspace,
  onPaste,
  group,
  onGroupChange,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const keyHeight = padKeyHeight(height);
  const page: SymbolPage = group === "converter" || group === "pad" ? "basics" : group;
  const rows = useMemo(() => padRows(page), [page]);

  if (!open) return null;

  const cellKey = (cell: PadCell, at: string) => {
    if (cell.kind === "insert") {
      return (
        <MathKey
          key={at}
          label={cell.spec.label}
          testID={`math-key-${cell.spec.id}`}
          accessibilityLabel={symbolA11yLabel(cell.spec)}
          onPress={() => {
            hapticSelection();
            onInsert(cell.spec);
          }}
          height={keyHeight}
        />
      );
    }
    if (cell.kind === "backspace") {
      return (
        <MathKey
          key={at}
          icon="backspace"
          testID="math-key-backspace"
          accessibilityLabel={t("chat.math_keyboard_backspace")}
          onPress={() => {
            hapticSelection();
            onBackspace();
          }}
          height={keyHeight}
        />
      );
    }
    const direction = cell.kind;
    return (
      <MathKey
        key={at}
        icon={direction === "left" ? "caret-left" : "caret-right"}
        testID={`math-key-${direction}`}
        accessibilityLabel={t(`chat.math_keyboard_${direction}`)}
        onPress={() => {
          hapticSelection();
          onCaret(direction);
        }}
        height={keyHeight}
      />
    );
  };

  return (
    <View
      style={[s.pad, { height }]}
      accessibilityLabel={t("chat.math_keyboard_a11y")}
      testID="math-keyboard-pad"
    >
      <View style={s.tabs}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={s.tabRow}
          keyboardShouldPersistTaps="handled"
        >
          {MATH_KEYBOARD_GROUPS.map((id) => (
            <Chip
              key={id}
              variant="filter"
              label={t(`chat.math_keyboard_group_${id}`)}
              selected={id === group}
              onPress={() => onGroupChange(id)}
              accessibilityRole="tab"
              testID={`math-keyboard-tab-${id}`}
            />
          ))}
        </ScrollView>
        <IconButton
          name="clipboard"
          size={IconSize.sm}
          color={theme.primary}
          onPress={() => {
            hapticSelection();
            onPaste();
          }}
          accessibilityLabel={t("chat.math_keyboard_paste")}
          testID="math-keyboard-paste"
        />
        <Button
          title={t("chat.math_keyboard_abc")}
          variant="ghost"
          size="sm"
          onPress={onToggle}
          accessibilityLabel={t("chat.math_keyboard_abc")}
          testID="math-keyboard-abc"
        />
      </View>
      <View style={s.keys}>
        {group === "converter" ? (
          <MathConverterPad
            keyHeight={keyHeight}
            onAsk={onAsk}
            onStop={onStop}
            streaming={streaming}
          />
        ) : (
          rows.map((row, r) => (
            <View key={r} style={s.row}>
              {row.map((cell, c) => cellKey(cell, `${r}-${c}`))}
            </View>
          ))
        )}
      </View>
    </View>
  );
});

const makeStyles = (theme: Theme) =>
  StyleSheet.create({
    pad: {
      marginTop: Space.xs,
      marginHorizontal: -Space.sm,
      paddingHorizontal: Space.xs,
      paddingTop: Space.xs,
      paddingBottom: Space.sm,
      backgroundColor: theme.surfaceAlt,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: theme.border,
      overflow: "hidden",
      gap: PAD_GAP,
    },
    tabs: {
      height: TAB_ROW_HEIGHT,
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xxs,
    },
    tabRow: { flexDirection: "row", alignItems: "center", gap: Space.xxs, paddingRight: Space.xxs },
    keys: { flex: 1, gap: PAD_GAP },
    row: { flexDirection: "row", gap: PAD_GAP },
  });
