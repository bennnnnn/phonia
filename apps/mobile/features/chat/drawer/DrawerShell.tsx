/**
 * Custom slide drawer. Chat stays mounted; the sidebar slides in from the
 * left. Open via the header button, Android back, or an interactive swipe
 * from the left edge; close via scrim tap, back, or by dragging the panel.
 *
 * Edge open uses Gesture.Pan with manualActivation (same claim rules as the
 * old PanResponder) so taps on the header menu button are not stolen by an
 * opaque left-edge hit strip. When the drawer is open, a horizontal drag on
 * the panel itself moves it (vertical list scroll still wins).
 */
/* eslint-disable react-hooks/immutability -- Reanimated shared values are mutated on the UI thread by design */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  AccessibilityInfo,
  BackHandler,
  findNodeHandle,
  Keyboard,
  Pressable,
  StyleSheet,
  useWindowDimensions,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from "react-native-reanimated";

import { ConversationList } from "@/features/chat/drawer/ConversationList";
import { DrawerProvider } from "@/contexts/DrawerContext";
import { registerDrawer } from "@/features/chat/drawer/drawer";
import { cappedDrawerWidth } from "@/features/chat/drawer/drawerPan";
import { tap } from "@/lib/haptics";
import { useReduceMotion } from "@/lib/reduceMotion";
import { shadowOverlay } from "@/lib/shadow";
import { type Theme, useTheme } from "@/lib/theme";
import { useLatestRef } from "@/lib/latestRef";

/** Left-edge hit slop for swipe-to-open (pt). Must stay a local const — Reanimated worklets cannot read imported names here. */
const EDGE_WIDTH = 28;
/** Horizontal travel on the open panel before a touch becomes a drawer drag, not a press. */
const PANEL_DRAG = 24;
/** Fraction of drawer width that counts as "open enough" to finish open. */
const OPEN_PROGRESS = 0.35;
/** Horizontal velocity (px/s from RNGH) to fling open/closed. */
const FLING_VX = 800;

const SPRING = {
  damping: 28,
  stiffness: 280,
  // Without this the panel overshoots past 0, a strip of chat shows on the
  // left, then the drawer springs back — looks like the screen flashing through.
  overshootClamping: true,
} as const;

export function DrawerShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { width } = useWindowDimensions();
  const theme = useTheme();
  const reduceMotion = useReduceMotion();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const drawerWidth = cappedDrawerWidth(width);

  const translateX = useSharedValue(-drawerWidth);
  const overlayOpacity = useSharedValue(0);
  const dragStartX = useSharedValue(-drawerWidth);
  const widthSV = useSharedValue(drawerWidth);
  const isOpenSV = useSharedValue(0);
  const touchStartX = useSharedValue(0);
  const touchStartY = useSharedValue(0);
  const didActivate = useSharedValue(0);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerOpenRef = useLatestRef(drawerOpen);
  const panelRef = useRef<View>(null);

  useEffect(() => {
    widthSV.value = drawerWidth;
    if (!drawerOpenRef.current) {
      translateX.value = -drawerWidth;
    }
  }, [drawerWidth, translateX, widthSV, drawerOpenRef]);

  useEffect(() => {
    isOpenSV.value = drawerOpen ? 1 : 0;
  }, [drawerOpen, isOpenSV]);

  const settleTo = useCallback(
    (open: boolean, withHaptic: boolean) => {
      const w = widthSV.value;
      setDrawerOpen(open);
      drawerOpenRef.current = open;
      isOpenSV.value = open ? 1 : 0;
      if (withHaptic && open) tap();
      if (open) Keyboard.dismiss();
      if (reduceMotion) {
        translateX.value = open ? 0 : -w;
        overlayOpacity.value = open ? 1 : 0;
      } else {
        translateX.value = withSpring(open ? 0 : -w, SPRING);
        if (open) {
          // Cover chat immediately — a 200ms scrim fade lets the screen show
          // through while the panel is still sliding in.
          overlayOpacity.value = 1;
        } else {
          overlayOpacity.value = withTiming(0, { duration: 150 });
        }
      }
    },
    [isOpenSV, overlayOpacity, reduceMotion, translateX, widthSV, drawerOpenRef],
  );

  const settleToRef = useLatestRef(settleTo);

  const settleFromGesture = useCallback((openNext: boolean, withHaptic: boolean) => {
    settleToRef.current(openNext, withHaptic);
  }, [settleToRef]);

  const markOpen = useCallback(() => {
    setDrawerOpen(true);
    drawerOpenRef.current = true;
    isOpenSV.value = 1;
    Keyboard.dismiss();
  }, [isOpenSV, drawerOpenRef]);

  const open = useCallback(() => settleToRef.current(true, true), [settleToRef]);
  const close = useCallback(() => settleToRef.current(false, false), [settleToRef]);

  useEffect(() => registerDrawer(open, close, () => drawerOpenRef.current), [open, close, drawerOpenRef]);

  useEffect(() => {
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      if (!drawerOpenRef.current) return false;
      close();
      return true;
    });
    return () => sub.remove();
  }, [close, drawerOpenRef]);

  // A screen reader moves into the panel when it opens, as it does into a Sheet.
  useEffect(() => {
    if (!drawerOpen) return;
    const frame = requestAnimationFrame(() => {
      const tag = findNodeHandle(panelRef.current);
      if (tag != null) AccessibilityInfo.setAccessibilityFocus(tag);
    });
    return () => cancelAnimationFrame(frame);
  }, [drawerOpen]);

  // The builder runs in render, but its callbacks run on touch events; React's compiler
  // cannot tell them apart, so it reads their ref use as a render read.
  /* eslint-disable react-hooks/refs -- the gesture callbacks read refs on touch, not in render */
  const pan = useMemo(
    () =>
      Gesture.Pan()
        .manualActivation(true)
        .onBegin((e) => {
          // Window coords — view-local `e.x` is 0 for composer/mic taps and
          // looks like an edge swipe, which opens the drawer and then leaves
          // the panel on screen with React still "closed" (taps fall through).
          touchStartX.value = e.absoluteX;
          touchStartY.value = e.absoluteY;
          didActivate.value = 0;
        })
        .onTouchesMove((e, manager) => {
          const t = e.changedTouches[0];
          if (!t) return;
          const dx = t.absoluteX - touchStartX.value;
          const dy = t.absoluteY - touchStartY.value;
          // Wait for a clear move before claiming (lets header taps through).
          if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return;
          if (Math.abs(dy) >= Math.abs(dx)) {
            manager.fail();
            return;
          }
          const w = widthSV.value;
          const openNow = isOpenSV.value > 0.5;
          // Inline, not an imported helper: worklets cannot close over
          // imported helpers without a Hermes "Property doesn't exist" crash.
          // A short slide on a row is a press, not a drawer drag.
          const onPanel = openNow && touchStartX.value < w && Math.abs(dx) >= PANEL_DRAG;
          const onScrimClose = openNow && touchStartX.value >= w && dx < 0;
          const onEdgeOpen = !openNow && touchStartX.value <= EDGE_WIDTH && dx > 0;
          if (onPanel || onScrimClose || onEdgeOpen) {
            manager.activate();
          } else {
            manager.fail();
          }
        })
        // A tap never moves enough to activate. Fail on release so the button
        // underneath gets the press — otherwise the undecided pan swallows it
        // and search, New chat, and the nav rows do nothing.
        .onTouchesUp((_e, manager) => {
          if (didActivate.value === 0) manager.fail();
        })
        .onTouchesCancelled((_e, manager) => {
          if (didActivate.value === 0) manager.fail();
        })
        .onStart(() => {
          didActivate.value = 1;
          dragStartX.value = translateX.value;
          if (isOpenSV.value < 0.5) {
            runOnJS(markOpen)();
          }
        })
        .onUpdate((e) => {
          const w = widthSV.value;
          const next = Math.max(-w, Math.min(0, dragStartX.value + e.translationX));
          translateX.value = next;
          overlayOpacity.value = 1 + next / w;
        })
        .onEnd((e) => {
          const w = widthSV.value;
          const next = Math.max(-w, Math.min(0, dragStartX.value + e.translationX));
          const progress = 1 + next / w;
          const flingOpen = e.velocityX > FLING_VX;
          const flingClose = e.velocityX < -FLING_VX;
          const shouldOpen = flingOpen || (!flingClose && progress >= OPEN_PROGRESS);
          runOnJS(settleFromGesture)(shouldOpen, shouldOpen && progress < 1);
        })
        .onFinalize((_e, success) => {
          // Only settle cancelled *active* drags — never after a failed claim,
          // or a header menu tap would race settle(false) against open().
          if (!success && didActivate.value) {
            const progress = 1 + translateX.value / widthSV.value;
            runOnJS(settleFromGesture)(progress >= OPEN_PROGRESS, false);
          }
          didActivate.value = 0;
        }),
    [
      didActivate,
      dragStartX,
      isOpenSV,
      markOpen,
      overlayOpacity,
      settleFromGesture,
      touchStartX,
      touchStartY,
      translateX,
      widthSV,
    ],
  );
  /* eslint-enable react-hooks/refs */

  const drawerStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: translateX.value }],
  }));

  const overlayStyle = useAnimatedStyle(() => ({
    opacity: overlayOpacity.value,
  }));

  const isOpenNow = useCallback(() => drawerOpenRef.current, [drawerOpenRef]);
  const drawerControls = useMemo(() => ({ open, close, isOpenNow }), [open, close, isOpenNow]);

  return (
    <DrawerProvider controls={drawerControls} isOpen={drawerOpen}>
      <GestureDetector gesture={pan}>
        <View style={s.root}>
          <View style={s.rootInner}>
            {/* A screen reader reaches one side at a time: the chat, or the open panel. */}
            <View
              style={[
                s.content,
                drawerOpen && s.contentBehind,
                { pointerEvents: drawerOpen ? "none" : "auto" },
              ]}
              accessibilityElementsHidden={drawerOpen}
              importantForAccessibility={drawerOpen ? "no-hide-descendants" : "auto"}
            >
              {children}
            </View>

            <Animated.View
              style={[
                s.overlay,
                { backgroundColor: theme.scrim },
                overlayStyle,
                { pointerEvents: "none" },
              ]}
            />

            <Animated.View
              style={[
                s.tapClose,
                overlayStyle,
                { pointerEvents: drawerOpen ? "auto" : "none" },
              ]}
            >
              <Pressable
                style={StyleSheet.absoluteFill}
                onPress={close}
                accessible={drawerOpen}
                accessibilityRole="button"
                accessibilityLabel={t("common.close")}
              />
            </Animated.View>

            <Animated.View
              ref={panelRef}
              accessibilityViewIsModal={drawerOpen}
              accessibilityElementsHidden={!drawerOpen}
              importantForAccessibility={drawerOpen ? "auto" : "no-hide-descendants"}
              onAccessibilityEscape={close}
              style={[
                s.drawer,
                {
                  width: drawerWidth,
                  backgroundColor: theme.bg,
                  // Always receive hits while on-screen. Gating on React
                  // `drawerOpen` left a visible panel with pointerEvents none
                  // after a bad edge claim — New chat then focused the composer.
                  pointerEvents: "auto",
                },
                drawerStyle,
              ]}
            >
              <ConversationList />
            </Animated.View>
          </View>
        </View>
      </GestureDetector>
    </DrawerProvider>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    root: { flex: 1 },
    rootInner: { flex: 1 },
    content: { flex: 1, zIndex: 1 },
    contentBehind: { zIndex: 0 },
    overlay: {
      ...StyleSheet.absoluteFill,
      zIndex: 150,
    },
    tapClose: {
      ...StyleSheet.absoluteFill,
      zIndex: 160,
    },
    drawer: {
      position: "absolute",
      top: 0,
      bottom: 0,
      left: 0,
      ...shadowOverlay(theme),
      // Side panel casts onto chat to the right, not down like a floating menu.
      shadowOffset: { width: 4, height: 0 },
      zIndex: 200,
      overflow: "hidden",
    },
  });
}
