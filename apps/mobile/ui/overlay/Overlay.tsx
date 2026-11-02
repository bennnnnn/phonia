import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Modal, Platform, Pressable, StyleSheet, View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
  type SharedValue,
} from "react-native-reanimated";
import { FullWindowOverlay } from "react-native-screens";
import { useTranslation } from "react-i18next";

import { Motion, useReduceMotion } from "@/lib/motion";
import { useTheme } from "@/lib/theme";

/** How long the exit fade runs before the layer unmounts. */
export const OVERLAY_EXIT_MS = 150;

const ProgressContext = createContext<SharedValue<number> | null>(null);

/**
 * 0 → 1 as the layer opens, 1 → 0 as it closes. Menus, dialogs and pickers
 * derive their own scale/fade from it so every popup moves the same way.
 */
export function useOverlayProgress(): SharedValue<number> {
  const progress = useContext(ProgressContext);
  if (!progress) throw new Error("useOverlayProgress must be used inside <Overlay>");
  return progress;
}

type Props = {
  visible: boolean;
  /** Scrim tap and Android back. Ignored when `dismissible` is false. */
  onRequestClose: () => void;
  /** `wash` softens the page (menus); `dim` darkens it (dialogs, pickers). */
  scrim?: "wash" | "dim";
  dismissible?: boolean;
  children: ReactNode;
  testID?: string;
};

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

/**
 * The one layer every popup floats in. iOS draws it in a window above the
 * app (`FullWindowOverlay`), so it opens over sheets and other modals without
 * iOS's "one presented modal at a time" limit; Android uses a transparent
 * Modal, which already stacks. The layer stays mounted through its exit fade,
 * but stops taking touches and leaves the accessibility tree immediately.
 */
export function Overlay({
  visible,
  onRequestClose,
  scrim = "dim",
  dismissible = true,
  children,
  testID,
}: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const reduceMotion = useReduceMotion();
  const progress = useSharedValue(0);
  const [mounted, setMounted] = useState(visible);

  useEffect(() => {
    if (visible) {
      setMounted(true);
      progress.value = reduceMotion ? 1 : withSpring(1, Motion.spring.popover);
      return;
    }
    progress.value = reduceMotion
      ? 0
      : withTiming(0, { duration: OVERLAY_EXIT_MS, easing: Motion.easing.in });
    const timer = setTimeout(() => setMounted(false), reduceMotion ? 0 : OVERLAY_EXIT_MS);
    return () => clearTimeout(timer);
  }, [visible, reduceMotion, progress]);

  const scrimStyle = useAnimatedStyle(() => ({
    opacity: Math.min(1, Math.max(0, progress.value)),
  }));

  if (!visible && !mounted) return null;
  const closing = !visible;
  const requestClose = () => {
    if (dismissible && !closing) onRequestClose();
  };

  const layer = (
    <GestureHandlerRootView style={styles.fill}>
      <View
        style={styles.fill}
        pointerEvents={closing ? "none" : "box-none"}
        accessibilityElementsHidden={closing}
        importantForAccessibility={closing ? "no-hide-descendants" : "auto"}
        testID={testID}
      >
        <AnimatedPressable
          style={[
            styles.fill,
            { backgroundColor: scrim === "wash" ? theme.wash : theme.scrim },
            scrimStyle,
          ]}
          onPress={requestClose}
          accessible={dismissible}
          accessibilityRole={dismissible ? "button" : undefined}
          accessibilityLabel={dismissible ? t("common.close") : undefined}
          testID={testID ? `${testID}-scrim` : "overlay-scrim"}
        />
        <ProgressContext.Provider value={progress}>{children}</ProgressContext.Provider>
      </View>
    </GestureHandlerRootView>
  );

  if (Platform.OS === "ios") return <FullWindowOverlay>{layer}</FullWindowOverlay>;
  return (
    <Modal
      visible
      transparent
      statusBarTranslucent
      navigationBarTranslucent
      animationType="none"
      onRequestClose={requestClose}
    >
      {layer}
    </Modal>
  );
}

const styles = StyleSheet.create({
  fill: { ...StyleSheet.absoluteFill },
});
