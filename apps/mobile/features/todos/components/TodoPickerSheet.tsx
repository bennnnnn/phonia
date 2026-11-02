/**
 * Floating choice popup for the to-do editor (centered card): a category
 * list.
 */
import { useMemo, type ReactNode } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Sheet } from "@/ui/overlay/Sheet";
import { Icon } from "@/ui/icons/Icon";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { IconSize } from "@/ui/icons/sizes";

type Option = { key: string; label: string; disabled?: boolean; note?: string };

type Props = {
  visible: boolean;
  options?: Option[];
  selectedKey?: string;
  disabled?: boolean;
  /** Extra row under the choices, such as naming a new category. */
  footer?: ReactNode;
  keyboardAvoiding?: boolean;
  onClose: () => void;
  onSelect?: (key: string) => void;
};

function PickerBody({
  options = [],
  selectedKey = "",
  disabled,
  footer,
  onClose,
  onSelect,
}: Omit<Props, "visible" | "keyboardAvoiding">) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const locked = Boolean(disabled);

  return (
    <ScrollView
      style={s.scroll}
      bounces={false}
      showsVerticalScrollIndicator={false}
      testID="settings-picker-sheet"
    >
      {options.map((option) => {
        const active = option.key === selectedKey;
        const optionDisabled = locked || Boolean(option.disabled);
        return (
          <Pressable
            key={option.key}
            style={({ pressed }) => [s.option, pressed && !optionDisabled && s.optionPressed]}
            disabled={optionDisabled}
            accessibilityRole="radio"
            accessibilityState={{ selected: active, disabled: optionDisabled }}
            accessibilityLabel={option.label}
            onPress={() => {
              if (optionDisabled || !onSelect) return;
              if (!active) onSelect(option.key);
              onClose();
            }}
          >
            <Text style={[s.optionText, optionDisabled && s.optionTextDisabled]}>{option.label}</Text>
            {active ? (
              <Icon name="check" size={IconSize.md} color={theme.primary} />
            ) : option.note ? (
              <Text style={s.optionNote}>{option.note}</Text>
            ) : null}
          </Pressable>
        );
      })}
      {footer ? <View style={s.option}>{footer}</View> : null}
    </ScrollView>
  );
}

export function TodoPickerSheet({
  visible,
  keyboardAvoiding = false,
  onClose,
  ...rest
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);

  return (
    <Sheet
      visible={visible}
      onClose={onClose}
      variant="center"
      withHandle={false}
      keyboardAvoiding={keyboardAvoiding}
      contentContainerStyle={s.sheet}
    >
      <PickerBody {...rest} onClose={onClose} />
    </Sheet>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    sheet: {
      backgroundColor: t.bg,
      borderRadius: Radius.dialog,
      width: "86%",
      maxWidth: 340,
      padding: 0,
    },
    scroll: {
      maxHeight: 360,
    },
    option: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      gap: Space.md,
      minHeight: 56,
      padding: Space.md,
      backgroundColor: t.bg,
    },
    optionPressed: {
      backgroundColor: t.surfaceAlt,
    },
    optionText: {
      flex: 1,
      ...Type.body,
      color: t.text,
    },
    optionTextDisabled: {
      color: t.textTertiary,
    },
    optionNote: {
      ...Type.caption,
      color: t.primary,
      ...Weight.semibold,
    },
  });
}
