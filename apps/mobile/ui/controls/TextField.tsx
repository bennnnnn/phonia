import { useMemo, useState, type Ref } from "react";
import {
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from "react-native";

import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

import { useLiveAnnouncement } from "../hooks/useLiveAnnouncement";

type Props = Omit<TextInputProps, "style"> & {
  /** Shown above the box. */
  label?: string;
  /** Muted line under the box. */
  helper?: string;
  /** Replaces the helper in red and turns the border red. */
  error?: string | null;
  /** Layout for the whole field (label, box, helper). */
  style?: StyleProp<ViewStyle>;
  ref?: Ref<TextInput>;
};

/**
 * The app's text box: one height, one corner, one border that turns indigo
 * while typing and red on an error. Multiline fields grow from four lines.
 */
export function TextField({
  label,
  helper,
  error,
  style,
  multiline,
  onFocus,
  onBlur,
  placeholderTextColor,
  accessibilityLabel,
  ref,
  ...input
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [focused, setFocused] = useState(false);
  const note = error || helper;
  useLiveAnnouncement(error);

  return (
    <View style={[s.field, style]}>
      {label ? <Text style={s.label}>{label}</Text> : null}
      <TextInput
        ref={ref}
        {...input}
        multiline={multiline}
        placeholderTextColor={placeholderTextColor ?? theme.textTertiary}
        accessibilityLabel={accessibilityLabel ?? label}
        onFocus={(event) => {
          setFocused(true);
          onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          onBlur?.(event);
        }}
        style={[
          s.box,
          multiline && s.multiline,
          focused && s.focused,
          error ? s.errorBox : null,
        ]}
      />
      {note ? (
        <Text
          style={[s.note, error ? s.errorNote : null]}
          accessibilityLiveRegion={error ? "polite" : undefined}
        >
          {note}
        </Text>
      ) : null}
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    field: { gap: Space.xs },
    label: { ...Type.label, color: t.textSecondary },
    box: {
      ...Type.body,
      color: t.text,
      minHeight: Space.xl + Space.gutter,
      paddingHorizontal: Space.md,
      paddingVertical: Space.sm,
      borderRadius: Radius.lg,
      borderWidth: 1,
      borderColor: t.border,
      backgroundColor: t.surface,
    },
    multiline: { minHeight: Space.xl * 3, textAlignVertical: "top" },
    focused: { borderColor: t.primary },
    errorBox: { borderColor: t.danger },
    note: { ...Type.caption, color: t.textSecondary },
    errorNote: { color: t.danger },
  });
}
