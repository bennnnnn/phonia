import { useMemo } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { ActionShimmer } from "../feedback/ActionShimmer";
import { Icon } from "../icons/Icon";
import type { IconName } from "../icons/names";
import { IconSize } from "../icons/sizes";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

/**
 * `media`: a white pill with black ink, for chrome over a photo (the viewer's Share).
 * `bubble`: the user's message-bubble tint with its text colour, so it follows their
 * accent; for the one action inside a card in a reply (a clarify card's "Find my best
 * country").
 */
type Variant = "primary" | "secondary" | "outline" | "ghost" | "destructive" | "media" | "bubble";
/** sm 36 (inline actions), md 44 (default), lg 52 (a screen's main action). */
type Size = "sm" | "md" | "lg";

type Props = {
  title: string;
  onPress: () => void;
  variant?: Variant;
  size?: Size;
  /** Icon beside the label, e.g. `arrow-right` on a get-started button. */
  icon?: IconName;
  iconPlacement?: "start" | "end";
  loading?: boolean;
  loadingLabel?: string;
  disabled?: boolean;
  accessibilityLabel?: string;
  /** Layout-only overrides (e.g. `{ flex: 1 }` in action rows). */
  style?: StyleProp<ViewStyle>;
  testID?: string;
};

/**
 * The app's button: a pill in seven variants and three sizes, with an optional
 * leading icon. Leave specialized controls alone (send circle, branded auth).
 */
export function Button({
  title,
  onPress,
  variant = "primary",
  size = "md",
  icon,
  iconPlacement = "start",
  loading = false,
  loadingLabel,
  disabled = false,
  accessibilityLabel,
  style,
  testID,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const blocked = disabled || loading;
  const ink =
    variant === "primary" || variant === "destructive"
      ? theme.onPrimary
      : variant === "media"
        ? theme.mediaScrim
        : variant === "bubble"
          ? theme.text
          : variant === "ghost"
            ? theme.primary
            : theme.textSecondary;
  const spinner =
    variant === "primary" || variant === "destructive"
      ? theme.onPrimary
      : variant === "media"
        ? theme.mediaScrim
        : variant === "bubble"
          ? theme.text
          : theme.primary;

  return (
    <Pressable
      style={({ pressed }) => [
        s.base,
        size === "sm" && s.small,
        size === "lg" && s.large,
        variant === "primary" && s.primary,
        (variant === "secondary" || variant === "outline") && s.outline,
        variant === "ghost" && s.ghost,
        variant === "destructive" && s.destructive,
        variant === "media" && s.media,
        variant === "bubble" && s.bubble,
        blocked && s.disabled,
        pressed && !blocked && variant === "primary" && s.pressedPrimary,
        pressed &&
          !blocked &&
          (variant === "destructive" || variant === "media" || variant === "bubble") &&
          s.pressedDestructive,
        pressed &&
          !blocked &&
          variant !== "primary" &&
          variant !== "destructive" &&
          variant !== "media" &&
          variant !== "bubble" &&
          s.pressed,
        style,
      ]}
      onPress={onPress}
      disabled={blocked}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? (loading && loadingLabel ? loadingLabel : title)}
      accessibilityState={{ disabled: blocked, busy: loading }}
      testID={testID}
    >
      {loading && loadingLabel ? (
        <ActionShimmer
          label={loadingLabel}
          color={spinner}
          compact
          delayMs={220}
          textStyle={s.loadingLabel}
        />
      ) : loading ? (
        <ActivityIndicator color={spinner} />
      ) : (
        <>
          {icon && iconPlacement === "start" ? <Icon name={icon} size={IconSize.sm} color={ink} /> : null}
          <Text
            style={[
              s.label,
              size === "sm" && s.labelSmall,
              size === "lg" && s.labelLarge,
              variant === "primary" && s.labelPrimary,
              (variant === "secondary" || variant === "outline") && s.labelOutline,
              variant === "ghost" && s.labelGhost,
              variant === "destructive" && s.labelPrimary,
              variant === "media" && s.labelMedia,
              variant === "bubble" && s.labelBubble,
            ]}
          >
            {title}
          </Text>
          {icon && iconPlacement === "end" ? <Icon name={icon} size={IconSize.sm} color={ink} /> : null}
        </>
      )}
    </Pressable>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    base: {
      minHeight: Space.minTouch,
      borderRadius: Radius.full,
      paddingHorizontal: Space.gutter,
      paddingVertical: Space.sm,
      flexDirection: "row",
      gap: Space.xs,
      alignItems: "center",
      justifyContent: "center",
    },
    small: {
      minHeight: Space.xl + Space.xxs,
      paddingHorizontal: Space.md,
      paddingVertical: Space.xs,
    },
    large: {
      minHeight: Space.xl + Space.gutter,
      paddingHorizontal: Space.lg,
    },
    primary: {
      backgroundColor: theme.primary,
    },
    outline: {
      backgroundColor: "transparent",
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
    },
    ghost: {
      backgroundColor: "transparent",
      minHeight: 44,
      paddingVertical: Space.xs,
    },
    destructive: {
      backgroundColor: theme.danger,
    },
    media: {
      backgroundColor: theme.onMedia,
    },
    // The user's own bubble tint, so it follows their accent like their messages do.
    bubble: {
      backgroundColor: theme.userBubble,
    },
    disabled: {
      opacity: 0.55,
    },
    pressed: {
      opacity: 0.72,
    },
    pressedPrimary: {
      backgroundColor: theme.primaryDark,
    },
    pressedDestructive: {
      opacity: 0.88,
    },
    label: {
      ...Type.body,
      ...Weight.semibold,
    },
    labelSmall: { ...Type.label, ...Weight.semibold },
    labelLarge: { ...Weight.bold },
    labelPrimary: {
      color: theme.onPrimary,
    },
    labelMedia: {
      color: theme.mediaScrim,
    },
    labelBubble: {
      color: theme.text,
    },
    labelOutline: {
      color: theme.textSecondary,
      ...Weight.semibold,
    },
    labelGhost: {
      ...Type.callout,
      color: theme.primary,
    },
    loadingLabel: {
      ...Type.callout,
      ...Weight.bold,
    },
  });
}
