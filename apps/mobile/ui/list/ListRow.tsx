import { useMemo, type ReactNode, type Ref } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Switch,
  Text,
  View,
  type AccessibilityActionEvent,
  type AccessibilityActionInfo,
  type GestureResponderEvent,
  type StyleProp,
  type TextProps,
  type ViewStyle,
} from "react-native";

import { selection } from "@/lib/haptics";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

import { Icon } from "../icons/Icon";
import type { IconName } from "../icons/names";
import { IconSize } from "../icons/sizes";

type Props = {
  title: string;
  /** Muted line under the title. */
  subtitle?: string;
  /** The row's current value, under the title (Settings style). */
  value?: string;
  /** A value on the right, as text or in a capsule (a to-do's date and time). */
  detail?: string;
  detailStyle?: "text" | "pill";
  icon?: IconName;
  /** Custom leading art (avatar, brand mark). Wins over `icon`. */
  leading?: ReactNode;
  iconColor?: string;
  /** What sits at the far right. A switch row passes `switchValue` instead. */
  accessory?: "chevron" | "check";
  /** Makes the row a switch; the whole row toggles it. */
  switchValue?: boolean;
  onSwitchChange?: (next: boolean) => void;
  /** Shows a spinner at the right and blocks presses. */
  busy?: boolean;
  danger?: boolean;
  /** Indigo icon and title, for a row that invites an upgrade or a first step. */
  accent?: boolean;
  disabled?: boolean;
  /** For a row that opens a popover: says whether it is open. */
  expanded?: boolean;
  onPress?: () => void;
  /** Gets the touch, so a Menu can open where the finger is. */
  onLongPress?: (event: GestureResponderEvent) => void;
  /**
   * `grouped`: a block in a ListGroup (Settings). `plain`: no background,
   * for sheets, pickers and detail pages.
   */
  appearance?: "grouped" | "plain";
  /** Indents a row that belongs to the one above it. */
  inset?: boolean;
  /** Caps the title and the lines under it (one line each for a file list). */
  numberOfLines?: number;
  /** Where a capped title is cut: `middle` keeps a file name's extension. */
  ellipsizeMode?: TextProps["ellipsizeMode"];
  accessibilityLabel?: string;
  accessibilityHint?: string;
  /** Screen-reader actions, e.g. what the row's long-press menu offers. */
  accessibilityActions?: AccessibilityActionInfo[];
  onAccessibilityAction?: (event: AccessibilityActionEvent) => void;
  style?: StyleProp<ViewStyle>;
  testID?: string;
  /** Lets a Menu or SelectMenu open from this row. */
  ref?: Ref<View>;
};

/**
 * The one list row: Settings, sheets, pickers and detail pages all use it,
 * so rows keep one height, one icon size and one set of trailing controls.
 */
export function ListRow({
  title,
  subtitle,
  value,
  detail,
  detailStyle = "text",
  icon,
  leading,
  iconColor,
  accessory,
  switchValue,
  onSwitchChange,
  busy = false,
  danger = false,
  accent = false,
  disabled = false,
  expanded,
  onPress,
  onLongPress,
  appearance = "grouped",
  inset = false,
  numberOfLines,
  ellipsizeMode,
  accessibilityLabel,
  accessibilityHint,
  accessibilityActions,
  onAccessibilityAction,
  style,
  testID,
  ref,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const isSwitch = switchValue !== undefined;
  const tint = danger ? theme.danger : accent ? theme.primary : undefined;
  const rowStyle = [
    s.row,
    appearance === "grouped" ? s.grouped : s.plain,
    inset && s.inset,
    style,
  ];
  const pressedStyle = appearance === "grouped" ? s.pressed : s.plainPressed;

  const body = (
    <>
      {leading || icon ? (
        <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          {leading ??
            (icon ? (
              <Icon
                name={icon}
                size={appearance === "grouped" ? IconSize.md : IconSize.sm}
                color={iconColor ?? tint}
              />
            ) : null)}
        </View>
      ) : null}
      <View style={s.body}>
        <Text
          style={[s.title, tint ? { color: tint } : null]}
          numberOfLines={numberOfLines}
          ellipsizeMode={ellipsizeMode}
        >
          {title}
        </Text>
        {value ? <Text style={s.secondary} numberOfLines={numberOfLines}>{value}</Text> : null}
        {subtitle ? <Text style={s.secondary} numberOfLines={numberOfLines}>{subtitle}</Text> : null}
      </View>
      {detail && !busy ? (
        <View style={detailStyle === "pill" ? s.pill : s.detailBox}>
          <Text style={detailStyle === "pill" ? s.pillText : s.detailText} numberOfLines={1}>
            {detail}
          </Text>
        </View>
      ) : null}
      {busy ? (
        <View
          accessible={isSwitch}
          accessibilityRole={isSwitch ? "progressbar" : undefined}
          accessibilityState={isSwitch ? { busy: true } : undefined}
          accessibilityElementsHidden={!isSwitch}
          importantForAccessibility={isSwitch ? "auto" : "no-hide-descendants"}
        >
          <ActivityIndicator size="small" color={theme.primary} />
        </View>
      ) : isSwitch ? (
        <Switch
          value={switchValue}
          disabled={disabled}
          thumbColor={theme.bg}
          trackColor={{ false: theme.border, true: theme.primary }}
          onValueChange={onSwitchChange}
          pointerEvents="none"
          importantForAccessibility="no-hide-descendants"
          accessibilityElementsHidden
        />
      ) : accessory === "chevron" ? (
        <Icon name="chevron-right" size={IconSize.xs} color={theme.textTertiary} />
      ) : accessory === "check" ? (
        <Icon name="check" size={IconSize.sm} color={theme.primary} />
      ) : null}
    </>
  );

  if (isSwitch) {
    if (busy) return <View style={rowStyle} testID={testID}>{body}</View>;
    return (
      <Pressable
        ref={ref}
        style={({ pressed }) => [...rowStyle, pressed && pressedStyle]}
        accessibilityRole="switch"
        accessibilityLabel={accessibilityLabel ?? title}
        accessibilityHint={accessibilityHint ?? subtitle}
        accessibilityState={{ checked: switchValue, disabled }}
        disabled={disabled}
        onPress={() => {
          selection();
          onSwitchChange?.(!switchValue);
        }}
        testID={testID}
      >
        {body}
      </Pressable>
    );
  }

  if (!onPress && !onLongPress) {
    return (
      <View
        ref={ref}
        style={rowStyle}
        accessible={accessibilityLabel ? true : undefined}
        accessibilityRole="text"
        accessibilityLabel={accessibilityLabel}
        accessibilityHint={accessibilityHint}
        testID={testID}
      >
        {body}
      </View>
    );
  }

  return (
    <Pressable
      ref={ref}
      style={({ pressed }) => [...rowStyle, pressed && pressedStyle]}
      onPress={onPress}
      onLongPress={onLongPress}
      disabled={disabled || busy}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityHint={accessibilityHint}
      accessibilityState={{
        disabled: disabled || busy,
        busy,
        ...(accessory === "check" ? { selected: true } : null),
        ...(expanded === undefined ? null : { expanded }),
      }}
      accessibilityActions={accessibilityActions}
      onAccessibilityAction={onAccessibilityAction}
      testID={testID}
    >
      {body}
    </Pressable>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    row: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.md,
    },
    grouped: {
      minHeight: Space.xl + Space.lg,
      paddingHorizontal: Space.md,
      paddingVertical: Space.sm,
      borderRadius: Radius.row,
      backgroundColor: t.settingsSurface,
    },
    plain: {
      minHeight: Space.minTouch,
      gap: Space.sm,
      borderRadius: Radius.md,
    },
    plainPressed: { backgroundColor: t.pressed },
    inset: { paddingLeft: Space.xl },
    pressed: { opacity: 0.65 },
    body: { flex: 1, gap: 2 },
    title: { ...Type.body, color: t.text },
    secondary: { ...Type.secondary, color: t.textSecondary },
    detailBox: { maxWidth: "52%" },
    detailText: { ...Type.secondary, color: t.textSecondary, textAlign: "right" },
    pill: {
      maxWidth: "52%",
      borderRadius: Radius.sm,
      backgroundColor: t.elevated,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.xs,
    },
    pillText: { ...Type.secondary, color: t.text },
  });
}
