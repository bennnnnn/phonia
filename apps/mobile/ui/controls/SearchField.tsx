import type { ReactNode, Ref } from "react";
import { Pressable, StyleSheet, TextInput, View, type TextInputProps, type StyleProp, type ViewStyle } from "react-native";

import { Icon } from "../icons/Icon";
import { Radius } from "@/lib/radius";
import { shadowRaised } from "@/lib/shadow";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { IconSize } from "../icons/sizes";

type Props = {
  value: string;
  onChangeText: (text: string) => void;
  placeholder: string;
  inputRef?: Ref<TextInput>;
  /** Extra control inside the pill, after the field. */
  trailing?: ReactNode;
  onClear?: () => void;
  clearAccessibilityLabel?: string;
  clearTestID?: string;
  style?: StyleProp<ViewStyle>;
  autoFocus?: boolean;
  autoCapitalize?: TextInputProps["autoCapitalize"];
  autoCorrect?: boolean;
  returnKeyType?: TextInputProps["returnKeyType"];
  clearButtonMode?: TextInputProps["clearButtonMode"];
};

/** One search pill: white surface, soft shadow, search icon. */
export function SearchField({
  value,
  onChangeText,
  placeholder,
  inputRef,
  trailing,
  onClear,
  clearAccessibilityLabel,
  clearTestID,
  style,
  autoFocus,
  autoCapitalize = "none",
  autoCorrect = false,
  returnKeyType = "search",
  clearButtonMode,
}: Props) {
  const theme = useTheme();
  const s = makeStyles(theme);

  return (
    <View style={[s.bar, style]}>
      <Icon name="search" size={IconSize.sm} color={theme.text} />
      <TextInput
        ref={inputRef}
        style={s.input}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={theme.textDisabled}
        autoFocus={autoFocus}
        autoCapitalize={autoCapitalize}
        autoCorrect={autoCorrect}
        returnKeyType={returnKeyType}
        clearButtonMode={clearButtonMode}
      />
      {onClear && value.length > 0 ? (
        <Pressable
          onPress={onClear}
          accessibilityRole="button"
          accessibilityLabel={clearAccessibilityLabel}
          testID={clearTestID}
          hitSlop={{ top: 12, bottom: 12, left: Space.xs, right: Space.xs }}
        >
          <Icon name="close-circle" size={IconSize.sm} color={theme.textTertiary} />
        </Pressable>
      ) : null}
      {trailing}
    </View>
  );
}

function makeStyles(theme: ReturnType<typeof useTheme>) {
  return StyleSheet.create({
    bar: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      minHeight: Space.minTouch,
      borderRadius: Radius.full,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.xs,
      backgroundColor: theme.bg,
      ...shadowRaised(theme),
    },
    input: {
      flex: 1,
      ...Type.body,
      color: theme.text,
      paddingVertical: 0,
      minHeight: 22,
    },
  });
}
