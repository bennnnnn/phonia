import { useMemo, type ReactNode, type Ref } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { Space } from "@/lib/space";
import { type Theme, useTheme, withAlpha } from "@/lib/theme";

import { Icon } from "../icons/Icon";
import type { IconName } from "../icons/names";
import { IconSize } from "../icons/sizes";

/** Header buttons are 44 round: the touch target and the plate are the same circle. */
export const HEADER_BUTTON_SIZE = Space.minTouch;

type HeaderButtonVariant = "plate" | "plain" | "media";

type Props = {
  icon: IconName;
  onPress: () => void;
  accessibilityLabel: string;
  /**
   * `plate`: a round grey well (chat menu, back, close). `plain`: no well, for
   * buttons inside a HeaderButtonGroup. `media`: a see-through dark well with
   * a white icon, over photos and the camera.
   */
  variant?: HeaderButtonVariant;
  /** Shows a spinner in place of the icon and ignores presses. */
  busy?: boolean;
  disabled?: boolean;
  /** Icon color override (e.g. primary for a share action). */
  color?: string;
  style?: StyleProp<ViewStyle>;
  testID?: string;
  /** Lets a Menu drop from this button. */
  ref?: Ref<View>;
};

/**
 * The one header button: back (`arrow-left`), close, menu, ⋮. Every stack,
 * sheet toolbar and viewer uses it, so headers look the same across the app.
 */
export function HeaderButton({
  icon,
  onPress,
  accessibilityLabel,
  variant = "plate",
  busy = false,
  disabled = false,
  color,
  style,
  testID,
  ref,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const ink = color ?? (variant === "media" ? theme.onMedia : theme.text);

  return (
    <Pressable
      ref={ref}
      onPress={onPress}
      disabled={disabled || busy}
      hitSlop={variant === "plain" ? undefined : 4}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled: disabled || busy, busy }}
      testID={testID}
      style={({ pressed }) => [
        s.button,
        variant === "plate" && s.plate,
        variant === "media" && s.media,
        pressed && (variant === "plain" ? s.plainPressed : s.wellPressed),
        disabled && s.disabled,
        style,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={ink} size="small" testID={testID && `${testID}-busy`} />
      ) : (
        <Icon name={icon} size={IconSize.md} color={ink} testID={testID && `${testID}-icon`} />
      )}
    </Pressable>
  );
}

/** Two or more `plain` header buttons in one pill, like chat's new chat + ⋮. */
export function HeaderButtonGroup({
  children,
  style,
  testID,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  return (
    <View style={[s.group, style]} testID={testID}>
      {children}
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    button: {
      width: HEADER_BUTTON_SIZE,
      height: HEADER_BUTTON_SIZE,
      borderRadius: HEADER_BUTTON_SIZE / 2,
      alignItems: "center",
      justifyContent: "center",
    },
    plate: { backgroundColor: t.control },
    media: { backgroundColor: withAlpha(t.onMedia, 0.18) },
    wellPressed: { transform: [{ scale: 0.94 }], opacity: 0.85 },
    plainPressed: { backgroundColor: t.pressed },
    disabled: { opacity: 0.4 },
    group: {
      flexDirection: "row",
      alignItems: "center",
      borderRadius: HEADER_BUTTON_SIZE / 2,
      backgroundColor: t.control,
      overflow: "hidden",
    },
  });
}
