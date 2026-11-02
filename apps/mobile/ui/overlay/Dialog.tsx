import { useEffect, useMemo, useRef, type ReactNode } from "react";
import {
  AccessibilityInfo,
  findNodeHandle,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import Animated, { useAnimatedStyle } from "react-native-reanimated";

import { tap } from "@/lib/haptics";
import { Radius } from "@/lib/radius";
import { shadowOverlay } from "@/lib/shadow";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

import { useKeyboardHeight } from "../hooks/useKeyboardHeight";
import { Overlay, useOverlayProgress } from "./Overlay";

type DialogActionStyle = "default" | "cancel" | "destructive" | "primary";

export type DialogAction = {
  label: string;
  onPress?: () => void;
  style?: DialogActionStyle;
  /** Greyed out and inert (e.g. OK while a typed time is invalid). */
  disabled?: boolean;
  testID?: string;
};

type Props = {
  visible: boolean;
  title: string;
  message?: string;
  /** Extra content between the message and the buttons (pickers use this). */
  children?: ReactNode;
  /** Buttons, left to right. Omit for a dialog whose content has its own. */
  actions?: DialogAction[];
  /** Shown at the start of the button row (the time picker's keyboard toggle). */
  footerStart?: ReactNode;
  /** `label` is the pickers' small "Select time" heading. */
  titleVariant?: "title" | "label";
  /** Lift the card above the keyboard (dialogs with a text field). */
  avoidKeyboard?: boolean;
  /** Scrim tap / Android back. */
  onClose: () => void;
  dismissible?: boolean;
  /** Content width. Defaults to 340 (narrower on small screens). */
  width?: number;
  testID?: string;
};

const DIALOG_WIDTH = 340;

/**
 * Centered card for decisions and messages: title, message, right-aligned
 * text buttons (Cancel · OK, like the Android clock picker). Destructive
 * buttons are red. Pressing a button runs it, then closes the dialog.
 */
export function Dialog(props: Props) {
  return (
    <Overlay
      visible={props.visible}
      onRequestClose={props.onClose}
      scrim="dim"
      dismissible={props.dismissible ?? true}
      testID={props.testID}
    >
      <DialogCard {...props} />
    </Overlay>
  );
}

function DialogCard({
  visible,
  title,
  message,
  children,
  actions = [],
  footerStart,
  titleVariant = "title",
  avoidKeyboard = false,
  onClose,
  width = DIALOG_WIDTH,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const progress = useOverlayProgress();
  const screen = useWindowDimensions();
  const keyboardHeight = useKeyboardHeight(visible && avoidKeyboard);
  const titleRef = useRef<Text>(null);
  const cardWidth = Math.min(width, screen.width - Space.lg * 2);
  const stacked =
    actions.length > 2 || actions.some((action) => action.label.length > 18);

  useEffect(() => {
    if (!visible) return;
    const frame = requestAnimationFrame(() => {
      const tag = findNodeHandle(titleRef.current);
      if (tag != null) AccessibilityInfo.setAccessibilityFocus(tag);
    });
    return () => cancelAnimationFrame(frame);
  }, [visible]);

  const cardStyle = useAnimatedStyle(() => {
    const p = Math.max(0, progress.value);
    return {
      opacity: Math.min(1, p),
      transform: [{ scale: 0.94 + 0.06 * p }],
    };
  });

  return (
    <View style={[s.center, { paddingBottom: Space.lg + keyboardHeight }]} pointerEvents="box-none">
      <Animated.View
        style={[s.card, { width: cardWidth }, cardStyle]}
        accessibilityViewIsModal
        onAccessibilityEscape={onClose}
        accessibilityRole={"alert" as const}
      >
        <Text
          ref={titleRef}
          style={titleVariant === "label" ? s.titleLabel : s.title}
          accessibilityRole="header"
        >
          {title}
        </Text>
        {message ? <Text style={s.message}>{message}</Text> : null}
        {children}
        {actions.length > 0 || footerStart ? (
          <View style={[s.footer, stacked && s.footerStacked]}>
            {footerStart ? <View style={s.footerStart}>{footerStart}</View> : null}
            <View style={[s.actions, stacked && s.actionsStacked]}>
              {actions.map((action) => (
                <Pressable
                  key={action.label}
                  style={({ pressed }) => [s.button, pressed && s.buttonPressed]}
                  onPress={() => {
                    tap();
                    action.onPress?.();
                    onClose();
                  }}
                  disabled={action.disabled}
                  accessibilityRole="button"
                  accessibilityLabel={action.label}
                  accessibilityState={action.disabled ? { disabled: true } : undefined}
                  testID={action.testID}
                >
                  <Text
                    style={[
                      s.buttonText,
                      action.style === "cancel" && s.buttonTextCancel,
                      action.style === "destructive" && s.buttonTextDestructive,
                      action.disabled && s.buttonTextDisabled,
                    ]}
                  >
                    {action.label}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        ) : null}
      </Animated.View>
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    center: {
      ...StyleSheet.absoluteFill,
      alignItems: "center",
      justifyContent: "center",
      padding: Space.lg,
    },
    card: {
      backgroundColor: t.elevated,
      borderRadius: Radius.dialog,
      borderWidth: t.isDark ? StyleSheet.hairlineWidth : 0,
      borderColor: t.separator,
      paddingTop: Space.lg,
      paddingHorizontal: Space.lg,
      paddingBottom: Space.sm,
      gap: Space.xs,
      ...shadowOverlay(t),
    },
    title: {
      ...Type.title,
      color: t.text,
    },
    titleLabel: {
      ...Type.label,
      color: t.textSecondary,
    },
    message: {
      ...Type.body,
      color: t.textSecondary,
    },
    footer: {
      flexDirection: "row",
      alignItems: "center",
      marginTop: Space.sm,
      marginRight: -Space.sm,
    },
    footerStacked: { alignItems: "flex-end" },
    footerStart: { flex: 1, alignItems: "flex-start", marginLeft: -Space.sm },
    actions: {
      flex: 1,
      flexDirection: "row",
      justifyContent: "flex-end",
      flexWrap: "wrap",
      gap: Space.xxs,
    },
    actionsStacked: {
      flexDirection: "column",
      alignItems: "flex-end",
    },
    button: {
      minHeight: Space.minTouch,
      paddingHorizontal: Space.sm,
      borderRadius: Radius.full,
      alignItems: "center",
      justifyContent: "center",
    },
    buttonPressed: { backgroundColor: t.pressed },
    buttonText: {
      ...Type.body,
      ...Weight.semibold,
      color: t.primary,
    },
    buttonTextCancel: { color: t.textSecondary },
    buttonTextDestructive: { color: t.danger },
    buttonTextDisabled: { color: t.textDisabled },
  });
}
