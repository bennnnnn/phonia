import { ReactNode, useEffect, useMemo, useRef } from "react";
import {
  AccessibilityInfo,
  Dimensions,
  findNodeHandle,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
  type AccessibilityRole,
  type StyleProp,
  type ViewStyle,
} from "react-native";
import { GestureDetector, GestureHandlerRootView } from "react-native-gesture-handler";
import Animated from "react-native-reanimated";
import { useTranslation } from "react-i18next";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useKeyboardHeight } from "../hooks/useKeyboardHeight";
import { useSheetPanDismiss } from "./useSheetPanDismiss";
import { useReduceMotion } from "@/lib/reduceMotion";
import { Layer } from "@/lib/layer";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";

type Props = {
  visible: boolean;
  onClose: () => void;
  /** "bottom" anchors to the bottom edge (slide); "center" floats mid-screen (fade). */
  variant?: "bottom" | "center";
  animation?: "slide" | "fade" | "none";
  /**
   * Lift the sheet above the OS keyboard. Uses Keyboard events (not
   * KeyboardAvoidingView) so Android Modals work — activity `resize` does not
   * apply inside RN Modal windows. Tall sheets (e.g. add reminder + date)
   * also get a max-height + scroll so the input is not pushed off-screen.
   */
  keyboardAvoiding?: boolean;
  /** Reset a keyboard-avoiding sheet to the top when this value changes. */
  scrollResetKey?: string | number;
  /** Render the grabber handle at the top of a bottom sheet. */
  withHandle?: boolean;
  /** Override the grabber color when using a different sheet surface. */
  handleColor?: string;
  /**
   * Scrim tap, hardware back, and pan-down all honor this. Defaults to true.
   * Pass false for a blocking sheet — onRequestClose is still wired.
   */
  backdropDismiss?: boolean;
  /** Optional tint for sheets that soften the background instead of dimming it. */
  backdropColor?: string;
  /** Extra bottom padding on top of the safe-area inset (e.g. 12 for action sheets). */
  minBottomPadding?: number;
  /**
   * Float above the bottom edge with side/bottom margins (not edge-to-edge).
   * Safe-area clearance is applied as margin so the last row stays visible.
   */
  floating?: boolean;
  /**
   * Extra lift for a floating panel, in addition to the safe area. The attach
   * sheet does not use this — it sits on the bottom edge and stacks above the
   * composer.
   */
  bottomOffset?: number;
  /** Style override for the panel (background, radius, padding). */
  contentContainerStyle?: StyleProp<ViewStyle>;
  /** iOS only. Fires after the modal has finished leaving, so another sheet can present. */
  onDismiss?: () => void;
  /** Fires once the sheet is up, so something can present on top of it (the OS share menu). */
  onShow?: () => void;
  /**
   * Draw the sheet in the current screen instead of a Modal, so a real choice
   * Modal can open over it without moving this sheet.
   */
  embedded?: boolean;
  children: ReactNode;
};

export function Sheet({
  visible,
  onClose,
  variant = "bottom",
  animation,
  keyboardAvoiding = false,
  scrollResetKey,
  withHandle,
  handleColor,
  backdropDismiss = true,
  backdropColor,
  minBottomPadding = 0,
  floating = false,
  bottomOffset = 0,
  contentContainerStyle,
  onDismiss,
  onShow,
  embedded = false,
  children,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const keyboardHeight = useKeyboardHeight(keyboardAvoiding && visible);
  const reduceMotion = useReduceMotion();
  const dialogRef = useRef<View>(null);
  const scrollRef = useRef<ScrollView>(null);
  const dismissible = backdropDismiss;
  const { pan, panStyle } = useSheetPanDismiss(
    dismissible && variant === "bottom",
    reduceMotion,
    onClose,
  );

  const resolvedAnimation = reduceMotion
    ? "none"
    : (animation ?? (variant === "center" ? "fade" : "slide"));
  const showHandle = withHandle ?? variant === "bottom";
  const keyboardOpen = keyboardAvoiding && keyboardHeight > 0;
  // Android already shrinks an in-screen sheet when the keyboard opens.
  // A second inset on that path lifts the form twice. Modals and iOS still need it.
  const manualKeyboardInset = keyboardAvoiding && (Platform.OS === "ios" || !embedded);
  const windowHeight = Dimensions.get("window").height;
  const panelMaxHeight =
    manualKeyboardInset && variant === "bottom"
      ? Math.max(200, windowHeight - keyboardHeight - Math.max(insets.top, 12))
      : undefined;

  const requestClose = () => {
    if (dismissible) onClose();
  };

  useEffect(() => {
    if (!visible) return;
    const frame = requestAnimationFrame(() => {
      const tag = findNodeHandle(dialogRef.current);
      if (tag != null) AccessibilityInfo.setAccessibilityFocus(tag);
    });
    return () => cancelAnimationFrame(frame);
  }, [visible]);

  // An embedded sheet has no Modal to report when it is up.
  const onShowRef = useRef(onShow);
  onShowRef.current = onShow;
  useEffect(() => {
    if (visible && embedded) onShowRef.current?.();
  }, [visible, embedded]);

  useEffect(() => {
    if (!visible || !keyboardAvoiding) return;
    const frame = requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ y: 0, animated: false });
    });
    return () => cancelAnimationFrame(frame);
  }, [visible, keyboardAvoiding, scrollResetKey]);

  const body = keyboardAvoiding ? (
    <ScrollView
      ref={scrollRef}
      keyboardShouldPersistTaps="handled"
      bounces={false}
      showsVerticalScrollIndicator={false}
      contentContainerStyle={s.scrollContent}
    >
      {children}
    </ScrollView>
  ) : (
    children
  );

  const handle = showHandle ? (
    <View
      style={[s.handle, handleColor ? { backgroundColor: handleColor } : undefined]}
      testID="app-sheet-handle"
    />
  ) : null;

  const panel = (
    <View
      ref={dialogRef}
      accessibilityRole={"dialog" as AccessibilityRole}
      accessibilityViewIsModal
      // VoiceOver's two-finger scrub closes it, as the scrim and Android back do.
      onAccessibilityEscape={dismissible ? requestClose : undefined}
      testID="app-sheet-dialog"
      collapsable={false}
      style={[
        s.panel,
        variant === "bottom" && s.panelBottom,
        variant === "center" && s.panelCenter,
        variant === "bottom" &&
          (floating
            ? {
                marginHorizontal: Space.md,
                marginBottom: keyboardOpen
                  ? Space.sm
                  : floatingSheetBottomMargin({
                      safeAreaBottom: insets.bottom,
                      bottomOffset,
                    }),
                paddingBottom: Math.max(minBottomPadding, Space.sm),
                borderRadius: Radius.sheet,
              }
            : {
                paddingBottom: keyboardOpen
                  ? Math.max(minBottomPadding, 8)
                  : Math.max(insets.bottom, minBottomPadding),
              }),
        contentContainerStyle,
        panelMaxHeight != null && { maxHeight: panelMaxHeight },
      ]}
    >
      {dismissible && variant === "bottom" ? (
        <GestureDetector gesture={pan}>
          <Animated.View style={s.handleHit}>
            {handle ?? <View style={s.handleHitFill} />}
          </Animated.View>
        </GestureDetector>
      ) : (
        handle
      )}
      {body}
    </View>
  );

  const frame = (
    <View
      style={[
        s.overlay,
        variant === "center" && s.overlayCenter,
        manualKeyboardInset && variant === "bottom" && { paddingBottom: keyboardHeight },
      ]}
      testID={keyboardAvoiding ? "app-sheet-keyboard-host" : undefined}
    >
      <Pressable
        style={[s.backdrop, backdropColor ? { backgroundColor: backdropColor } : undefined]}
        onPress={dismissible ? requestClose : undefined}
        accessibilityLabel={dismissible ? t("common.close") : undefined}
        accessibilityRole={dismissible ? "button" : undefined}
        accessible={dismissible}
        testID="app-sheet-backdrop"
      />
      {dismissible && variant === "bottom" ? (
        <Animated.View style={panStyle}>{panel}</Animated.View>
      ) : (
        panel
      )}
    </View>
  );

  if (embedded) {
    if (!visible) return null;
    return (
      <View style={s.embedded} testID="app-sheet-embedded">
        {frame}
      </View>
    );
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType={resolvedAnimation}
      onRequestClose={requestClose}
      onDismiss={onDismiss}
      onShow={onShow}
      testID="app-sheet-modal"
    >
      <GestureHandlerRootView style={s.flex}>{frame}</GestureHandlerRootView>
    </Modal>
  );
}

/**
 * Bottom margin for a floating sheet. Safe-area clearance, plus `bottomOffset`
 * when a caller needs the panel to end higher than the home indicator.
 */
export function floatingSheetBottomMargin(options: {
  safeAreaBottom: number;
  bottomOffset?: number;
}): number {
  const safe = Math.max(options.safeAreaBottom, Space.xs) + Space.sm;
  const offset = options.bottomOffset ?? 0;
  if (offset <= 0) return safe;
  return Math.max(safe, offset + Space.sm);
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    flex: { flex: 1 },
    overlay: {
      flex: 1,
      justifyContent: "flex-end",
    },
    overlayCenter: {
      justifyContent: "center",
      alignItems: "center",
      padding: Space.lg,
    },
    backdrop: {
      ...StyleSheet.absoluteFill,
      backgroundColor: t.scrim,
    },
    panel: {
      overflow: "hidden",
    },
    panelBottom: {
      backgroundColor: t.bg,
      borderTopLeftRadius: Radius.sheet,
      borderTopRightRadius: Radius.sheet,
    },
    panelCenter: {
      backgroundColor: t.bg,
      borderRadius: Radius.sheet,
      width: "100%",
      maxWidth: 420,
    },
    handleHit: {
      minHeight: 24,
      alignItems: "center",
      justifyContent: "center",
    },
    handleHitFill: {
      height: 24,
    },
    handle: {
      alignSelf: "center",
      width: 36,
      height: 4,
      borderRadius: 2,
      backgroundColor: t.border,
      marginTop: Space.xs,
      marginBottom: Space.xxs,
    },
    scrollContent: {
      flexGrow: 0,
    },
    embedded: {
      position: "absolute",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      zIndex: Layer.sheet,
    },
  });
}
