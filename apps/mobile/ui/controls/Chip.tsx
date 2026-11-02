import { useMemo } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  View,
  type AccessibilityRole,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { selection } from "@/lib/haptics";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

import { Icon } from "../icons/Icon";
import type { IconName } from "../icons/names";
import { IconSize } from "../icons/sizes";

/**
 * - `assist`: a tappable suggestion (follow-up ideas).
 * - `filter`: one choice among several; `selected` turns it indigo.
 * - `input`: something the person added, with a remove button (skills).
 * - `tag`: a small read-only fact (salary, remote, a class's language).
 */
type ChipVariant = "assist" | "filter" | "input" | "tag";

type Props = {
  label: string;
  variant?: ChipVariant;
  icon?: IconName;
  /** Defaults to indigo on assist chips and to the label color otherwise. */
  iconColor?: string;
  /** Filter chips only. */
  selected?: boolean;
  onPress?: () => void;
  onLongPress?: () => void;
  /** Input chips: shows a remove button with this spoken label. */
  onRemove?: () => void;
  removeLabel?: string;
  /** Tag chips: a short muted lead-in before the label, e.g. "Pay". */
  prefix?: string;
  /** Assist chips may wrap a long suggestion onto a second line. */
  numberOfLines?: number;
  disabled?: boolean;
  /** Filter chips default to a radio when the choices exclude each other. */
  accessibilityRole?: Extract<AccessibilityRole, "button" | "radio" | "checkbox" | "tab">;
  accessibilityLabel?: string;
  accessibilityHint?: string;
  style?: StyleProp<ViewStyle>;
  testID?: string;
};

/** One chip for the whole app, so suggestions, filters, skills and tags match. */
export function Chip({
  label,
  variant = "assist",
  icon,
  iconColor,
  selected = false,
  onPress,
  onLongPress,
  onRemove,
  removeLabel,
  prefix,
  numberOfLines = 1,
  disabled = false,
  accessibilityRole = "button",
  accessibilityLabel,
  accessibilityHint,
  style,
  testID,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const on = variant === "input" || (variant === "filter" && selected);
  const ink = on ? theme.primary : variant === "tag" ? theme.textSecondary : theme.text;
  const iconInk = iconColor ?? (variant === "assist" ? theme.primary : ink);

  const content = (
    <>
      {icon ? <Icon name={icon} size={IconSize.xxs} color={iconInk} /> : null}
      <Text
        style={[
          variant === "tag" ? s.tagText : s.text,
          { color: ink },
          on && s.textOn,
        ]}
        numberOfLines={numberOfLines}
      >
        {prefix ? <Text style={s.prefix}>{`${prefix} `}</Text> : null}
        {label}
      </Text>
      {variant === "input" && onRemove ? (
        <Pressable
          onPress={onRemove}
          disabled={disabled}
          hitSlop={Space.xs}
          style={({ pressed }) => [s.remove, pressed && s.removePressed]}
          accessibilityRole="button"
          accessibilityLabel={removeLabel ?? label}
          testID={testID && `${testID}-remove`}
        >
          <Icon name="close" size={IconSize.xxs} color={theme.primary} />
        </Pressable>
      ) : null}
    </>
  );

  const shape = [
    s.base,
    variant === "tag" && s.tag,
    (variant === "assist" || variant === "filter") && s.touch,
    variant === "input" && s.input,
    on && s.on,
    disabled && s.disabled,
    style,
  ];

  // A filter is a selection, like a segment: one tick when the choice changes.
  const press = variant === "filter" && onPress
    ? () => {
        if (!selected || accessibilityRole === "checkbox") selection();
        onPress();
      }
    : onPress;

  if (!onPress && !onLongPress) {
    return (
      <View
        style={shape}
        testID={testID}
        accessible={variant !== "input"}
        accessibilityLabel={variant === "input" ? undefined : accessibilityLabel}
      >
        {content}
      </View>
    );
  }

  return (
    <Pressable
      onPress={press}
      onLongPress={onLongPress}
      disabled={disabled}
      style={({ pressed }) => [...shape, pressed && s.pressed]}
      accessibilityRole={accessibilityRole}
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityHint={accessibilityHint}
      accessibilityState={
        variant === "filter"
          ? accessibilityRole === "button" || accessibilityRole === "tab"
            ? { selected, disabled }
            : { checked: selected, disabled }
          : { disabled }
      }
      testID={testID}
    >
      {content}
    </Pressable>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    base: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xxs,
      maxWidth: "100%",
      borderRadius: Radius.full,
    },
    touch: {
      minHeight: Space.minTouch,
      paddingHorizontal: Space.md,
      paddingVertical: Space.xs,
      gap: Space.xs,
      backgroundColor: t.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
    },
    input: {
      minHeight: Space.minTouch - Space.xs,
      paddingLeft: Space.sm,
      paddingRight: Space.xxs,
      borderWidth: StyleSheet.hairlineWidth,
    },
    tag: {
      minHeight: Space.lg + Space.xxs,
      paddingHorizontal: Space.xs,
      backgroundColor: t.surfaceAlt,
    },
    on: { backgroundColor: t.primaryLight, borderColor: t.primary },
    pressed: { opacity: 0.72 },
    disabled: { opacity: 0.4 },
    text: { ...Type.secondary, ...Weight.medium, flexShrink: 1 },
    textOn: { ...Weight.semibold },
    tagText: { ...Type.compact, flexShrink: 1 },
    prefix: { ...Weight.bold, color: t.textTertiary },
    remove: {
      width: Space.lg + Space.xxs,
      height: Space.lg + Space.xxs,
      borderRadius: Radius.full,
      alignItems: "center",
      justifyContent: "center",
    },
    removePressed: { backgroundColor: t.pressed },
  });
}
