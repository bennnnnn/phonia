import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import {
  AccessibilityInfo,
  findNodeHandle,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import Animated, { useAnimatedStyle } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { selection } from "@/lib/haptics";
import { Radius } from "@/lib/radius";
import { shadowOverlay } from "@/lib/shadow";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

import { Icon } from "../icons/Icon";
import type { IconName } from "../icons/names";
import { IconSize } from "../icons/sizes";
import { Overlay, useOverlayProgress } from "./Overlay";
import { placePopover, type Rect } from "./placement";

type MenuItem = {
  key: string;
  label: string;
  icon?: IconName;
  /** A color dot in place of an icon — the accent color picker. */
  swatch?: string;
  onPress: () => void;
  /** Red ink — Delete and other actions that lose data. */
  destructive?: boolean;
  disabled?: boolean;
  /** Selectable menus: shows the check on the current choice. */
  selected?: boolean;
  /** `chevron` for rows that open more choices; a string shows a value. */
  trailing?: "chevron" | string;
  testID?: string;
};

export type MenuEntry = MenuItem | "separator";

type Props = {
  visible: boolean;
  onClose: () => void;
  items: MenuEntry[];
  /** The control that opened the menu; the card drops from it. */
  anchorRef?: RefObject<View | null>;
  /** Or a touch point (long-press) to open from. */
  anchorPoint?: { x: number; y: number } | null;
  /** Muted heading above the rows (e.g. the chat title). */
  title?: string;
  /** Rows are choices: radio semantics and a check on `selected`. */
  selectable?: boolean;
  width?: number;
  testID?: string;
};

const ROW_HEIGHT = 52;
const DEFAULT_WIDTH = 264;
/** A missing measurement never keeps the menu invisible for long. */
const MEASURE_TIMEOUT_MS = 120;

/**
 * The popover menu (ChatGPT's ⋮ card): one rounded card that grows from the
 * control you tapped, icon + label rows, destructive rows in red. The same
 * card lists choices when `selectable`, with a check on the current one.
 * Choosing a row closes the menu first, then runs the row's action, so the
 * action can open a sheet, dialog, or the system share sheet right away.
 */
export function Menu(props: Props) {
  return (
    <Overlay
      visible={props.visible}
      onRequestClose={props.onClose}
      scrim="wash"
      testID={props.testID}
    >
      <MenuCard {...props} />
    </Overlay>
  );
}

function MenuCard({
  visible,
  onClose,
  items,
  anchorRef,
  anchorPoint,
  title,
  selectable = false,
  width = DEFAULT_WIDTH,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const progress = useOverlayProgress();
  const screen = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const [anchor, setAnchor] = useState<Rect | null>(null);
  const [waitedForAnchor, setWaitedForAnchor] = useState(false);
  const [contentHeight, setContentHeight] = useState<number | null>(null);
  const firstRowRef = useRef<View>(null);

  useEffect(() => {
    if (!visible) return;
    if (anchorPoint) {
      setAnchor({ x: anchorPoint.x, y: anchorPoint.y, width: 0, height: 0 });
      return;
    }
    const node = anchorRef?.current;
    if (!node) return;
    node.measureInWindow((x, y, w, h) => setAnchor({ x, y, width: w, height: h }));
    const timer = setTimeout(() => setWaitedForAnchor(true), MEASURE_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [visible, anchorPoint, anchorRef]);

  const hasAnchor = Boolean(anchorPoint || anchorRef);
  const ready = !hasAnchor || anchor != null || waitedForAnchor;

  useEffect(() => {
    if (!visible || !ready) return;
    const frame = requestAnimationFrame(() => {
      const tag = findNodeHandle(firstRowRef.current);
      if (tag != null) AccessibilityInfo.setAccessibilityFocus(tag);
    });
    return () => cancelAnimationFrame(frame);
  }, [visible, ready]);

  const estimatedHeight =
    items.reduce((sum, entry) => sum + (entry === "separator" ? Space.xs + 1 : ROW_HEIGHT), 0) +
    (title ? ROW_HEIGHT - Space.xs : 0) +
    Space.xs * 2;
  const placement = placePopover({
    anchor: hasAnchor ? anchor : null,
    width,
    height: contentHeight ?? estimatedHeight,
    screen,
    insets,
  });

  const cardStyle = useAnimatedStyle(() => {
    const p = Math.max(0, progress.value);
    return {
      opacity: ready ? Math.min(1, p) : 0,
      transform: [{ scale: 0.9 + 0.1 * p }],
    };
  });

  const firstRowIndex = items.findIndex((entry) => entry !== "separator");
  const rows = items.map((entry, index) => {
    if (entry === "separator") {
      return <View key={`separator-${index}`} style={s.separator} />;
    }
    const isFirst = index === firstRowIndex;
    const ink = entry.destructive ? theme.danger : theme.text;
    return (
      <Pressable
        key={entry.key}
        ref={isFirst ? firstRowRef : undefined}
        style={({ pressed }) => [s.row, pressed && !entry.disabled && s.rowPressed]}
        disabled={entry.disabled}
        onPress={() => {
          selection();
          onClose();
          entry.onPress();
        }}
        accessibilityRole={selectable ? "radio" : "menuitem"}
        accessibilityLabel={entry.label}
        accessibilityState={{
          disabled: Boolean(entry.disabled),
          ...(selectable ? { checked: Boolean(entry.selected) } : null),
        }}
        testID={entry.testID}
      >
        {entry.swatch ? (
          <View style={[s.swatch, { backgroundColor: entry.swatch }]} />
        ) : entry.icon ? (
          <Icon
            name={entry.icon}
            size={IconSize.md}
            color={entry.disabled ? theme.textDisabled : ink}
          />
        ) : null}
        <Text
          style={[s.label, { color: entry.disabled ? theme.textDisabled : ink }]}
          numberOfLines={2}
        >
          {entry.label}
        </Text>
        {entry.selected ? (
          <Icon name="check" size={IconSize.sm} color={theme.primary} />
        ) : entry.trailing === "chevron" ? (
          <Icon name="chevron-right" size={IconSize.sm} color={theme.textTertiary} />
        ) : entry.trailing ? (
          <Text style={s.value} numberOfLines={1}>
            {entry.trailing}
          </Text>
        ) : null}
      </Pressable>
    );
  });

  return (
    <Animated.View
      style={[
        s.card,
        {
          top: placement.top,
          left: placement.left,
          width: Math.min(width, screen.width - Space.sm * 2),
          maxHeight: placement.maxHeight,
          transformOrigin: [placement.origin.x, placement.origin.y, 0],
        },
        cardStyle,
      ]}
      accessibilityViewIsModal
      onAccessibilityEscape={onClose}
      accessibilityRole={selectable ? "radiogroup" : "menu"}
    >
      {/* Shadow lives on the outer card. overflow:hidden there clips it, which
          left a white menu flat on a white page. */}
      <View style={[s.clip, { maxHeight: placement.maxHeight }]}>
        <ScrollView
          bounces={false}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={s.content}
          onContentSizeChange={(_w, h) => {
            const next = Math.round(h);
            if (next > 0 && next !== contentHeight) setContentHeight(next);
          }}
        >
          {title ? (
            <Text style={s.title} numberOfLines={2} accessibilityRole="header">
              {title}
            </Text>
          ) : null}
          {rows}
        </ScrollView>
      </View>
    </Animated.View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    card: {
      position: "absolute",
      backgroundColor: t.elevated,
      borderRadius: Radius.menu,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      ...shadowOverlay(t),
    },
    clip: {
      borderRadius: Radius.menu,
      overflow: "hidden",
    },
    content: { paddingVertical: Space.xs },
    title: {
      ...Type.secondary,
      ...Weight.semibold,
      color: t.textTertiary,
      paddingHorizontal: Space.gutter,
      paddingTop: Space.xs,
      paddingBottom: Space.xxs,
    },
    row: {
      minHeight: ROW_HEIGHT,
      flexDirection: "row",
      alignItems: "center",
      gap: Space.md,
      paddingHorizontal: Space.gutter,
      paddingVertical: Space.xs,
    },
    rowPressed: { backgroundColor: t.pressed },
    swatch: {
      width: IconSize.md,
      height: IconSize.md,
      borderRadius: IconSize.md / 2,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
    },
    label: {
      ...Type.navTitle,
      ...Weight.regular,
      flex: 1,
    },
    value: {
      ...Type.secondary,
      color: t.textSecondary,
      maxWidth: "40%",
    },
    separator: {
      height: StyleSheet.hairlineWidth,
      backgroundColor: t.separator,
      marginVertical: Space.xxs,
      marginHorizontal: Space.gutter,
    },
  });
}
