/* eslint-disable react-hooks/immutability -- Reanimated shared values are mutated on the UI thread by design */
import { useMemo } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Pressable as GHPressable } from "react-native-gesture-handler";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from "react-native-reanimated";
import type { EdgeInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { ScannerSubjectSwitcher } from "@/features/scanner/components/ScannerSubjectSwitcher";
import { IconSize } from "@/ui/icons/sizes";
import {
  SCANNER_SHUTTER_PX,
  SCANNER_SUBJECT_SWITCHER_PX,
  SCANNER_TOP_CONTROL_PX,
} from "@/lib/math/scannerRegion";
import { Motion, motionMs, useReduceMotion } from "@/lib/motion";
import { Radius } from "@/lib/radius";
import type { ScannerSubject } from "@/lib/scanner/subjects";
import { Space } from "@/lib/space";
import { Theme, useTheme, withAlpha } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { useLiveAnnouncement } from "@/ui/hooks/useLiveAnnouncement";

type Props = {
  insets: EdgeInsets;
  granted: boolean;
  preview: boolean;
  busy: boolean;
  /** Capture is in flight. Library picks stay off this so the shutter does not spin. */
  capturing?: boolean;
  /** False while the camera is still starting. A tap then is ignored, not a failure. */
  captureReady?: boolean;
  torchOn: boolean;
  subject: ScannerSubject;
  error: string | null;
  /** The reading review is open, so capture controls must not sit on top of it. */
  reviewing?: boolean;
  onClose: () => void;
  onSubjectChange: (subject: ScannerSubject) => void;
  onToggleTorch: () => void;
  /** Tap: the Photos picker. Long press (or the screen-reader action): the Files picker. */
  onOpenPhotos: () => void;
  onOpenFiles: () => void;
  onCapture: () => void;
  onRetake: () => void;
  onSolve: () => void;
};

export function MathScannerChrome({
  insets,
  granted,
  preview,
  busy,
  capturing = false,
  captureReady = true,
  torchOn,
  subject,
  error,
  reviewing = false,
  onClose,
  onSubjectChange,
  onToggleTorch,
  onOpenPhotos,
  onOpenFiles,
  onCapture,
  onRetake,
  onSolve,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const reduceMotion = useReduceMotion();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const shutterScale = useSharedValue(1);
  const pressMs = motionMs(Motion.duration.press, reduceMotion);

  const shutterStyle = useAnimatedStyle(() => ({
    transform: [{ scale: shutterScale.value }],
  }));

  const bottomPad = Math.max(insets.bottom, Space.md) + Space.sm;
  const errorBottom = bottomPad + SCANNER_SHUTTER_PX + SCANNER_SUBJECT_SWITCHER_PX + Space.xl;
  useLiveAnnouncement(error);

  const closeButton = (
    <Pressable
      style={s.topBtn}
      onPress={onClose}
      hitSlop={20}
      testID="math-scanner-close"
      accessibilityRole="button"
      accessibilityLabel={t("common.close")}
    >
      <Icon name="close" size={IconSize.md} color={theme.onMedia} />
    </Pressable>
  );

  if (reviewing) {
    return (
      <View style={s.closeLayer} pointerEvents="box-none">
        <View style={[s.topBar, { paddingTop: insets.top + Space.xs }]}>{closeButton}</View>
      </View>
    );
  }

  return (
    <View style={s.root} pointerEvents="box-none">
      {!preview ? (
        <View style={[s.topBar, { paddingTop: insets.top + Space.xs }]}>{closeButton}</View>
      ) : null}

      {error ? (
        <View style={[s.error, { bottom: errorBottom }]} testID="math-scanner-error">
          <Icon
            name="alert-circle"
            size={IconSize.sm}
            color={theme.onMedia}
            testID="math-scanner-error-icon"
          />
          <Text style={s.errorText} accessibilityLiveRegion="polite" accessibilityRole="alert">
            {error}
          </Text>
        </View>
      ) : null}

      {preview ? (
        <View style={[s.previewActions, { paddingBottom: bottomPad }]}>
          <GHPressable
            style={s.previewSecondary}
            onPress={onRetake}
            disabled={busy}
            accessibilityRole="button"
            accessibilityState={{ disabled: busy }}
            testID="math-scanner-preview-retake"
            accessibilityLabel={t("chat.math_scan_retake")}
          >
            <Text style={s.previewSecondaryText}>{t("chat.math_scan_retake")}</Text>
          </GHPressable>
          <GHPressable
            style={s.previewPrimary}
            onPress={onSolve}
            disabled={busy}
            accessibilityRole="button"
            accessibilityState={{ disabled: busy, busy }}
            testID="math-scanner-preview-solve"
            accessibilityLabel={t("chat.math_scan_solve")}
          >
            {busy ? (
              <ActivityIndicator color={theme.onPrimary} />
            ) : (
              <Text style={s.previewPrimaryText}>{t("chat.math_scan_solve")}</Text>
            )}
          </GHPressable>
        </View>
      ) : granted ? (
        <View style={[s.bottom, { paddingBottom: bottomPad }]}>
          <View style={s.bottomScrim} pointerEvents="none" />
          <ScannerSubjectSwitcher value={subject} onChange={onSubjectChange} />
          <View style={s.controls}>
            <GHPressable
              style={s.photosBtn}
              onPress={onOpenPhotos}
              onLongPress={onOpenFiles}
              disabled={busy}
              testID="math-scanner-photos"
              accessibilityRole="button"
              accessibilityState={{ disabled: busy }}
              accessibilityLabel={t("chat.math_scan_photos_a11y")}
              accessibilityHint={t("chat.math_scan_files_hint")}
              accessibilityActions={[{ name: "files", label: t("chat.math_scan_files_a11y") }]}
              onAccessibilityAction={(event) => {
                if (event.nativeEvent.actionName === "files") onOpenFiles();
              }}
            >
              <Icon name="image" size={IconSize.md} color={theme.onMedia} />
            </GHPressable>
            <GHPressable
              onPressIn={() => {
                shutterScale.value = withTiming(0.92, { duration: pressMs });
              }}
              onPressOut={() => {
                shutterScale.value = withTiming(1, { duration: pressMs });
              }}
              onPress={onCapture}
              disabled={busy || !captureReady}
              testID="math-scanner-shutter"
              accessibilityRole="button"
              accessibilityState={{ disabled: busy || !captureReady, busy }}
              accessibilityLabel={t("chat.math_scan_capture_a11y")}
            >
              <Animated.View style={[s.shutter, shutterStyle]}>
                {capturing ? (
                  <ActivityIndicator color={theme.text} />
                ) : (
                  <View style={s.shutterInner} testID="math-scanner-shutter-disc" />
                )}
              </Animated.View>
            </GHPressable>
            <View style={s.sideSlot}>
              <GHPressable
                style={[s.sideControl, torchOn ? s.torchOn : null]}
                onPress={onToggleTorch}
                disabled={busy}
                testID="math-scanner-torch"
                accessibilityRole="button"
                accessibilityState={{ selected: torchOn, disabled: busy }}
                accessibilityLabel={
                  torchOn ? t("chat.math_scan_torch_on_a11y") : t("chat.math_scan_torch_off_a11y")
                }
              >
                <Icon
                  name={torchOn ? "flashlight" : "flashlight-off"}
                  size={IconSize.md}
                  color={torchOn ? theme.primary : theme.onMedia}
                  style={s.torchIcon}
                />
              </GHPressable>
            </View>
          </View>
        </View>
      ) : null}
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    root: {
      ...StyleSheet.absoluteFill,
      zIndex: 40,
    },
    closeLayer: {
      ...StyleSheet.absoluteFill,
      zIndex: 60,
    },
    topBar: {
      position: "absolute",
      top: 0,
      left: Space.md,
      right: Space.md,
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "flex-start",
      zIndex: 50,
    },
    topBtn: {
      width: SCANNER_TOP_CONTROL_PX,
      height: SCANNER_TOP_CONTROL_PX,
      borderRadius: Radius.full,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: withAlpha(theme.mediaScrim, 0.55),
    },
    torchOn: {
      backgroundColor: withAlpha(theme.primary, 0.22),
    },
    torchIcon: {
      transform: [{ rotate: "-45deg" }],
    },
    // White ink and an icon: red on this scrim over a white page read 1.45:1.
    error: {
      position: "absolute",
      left: Space.md,
      right: Space.md,
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: Space.xs,
      backgroundColor: withAlpha(theme.mediaScrim, 0.65),
      paddingHorizontal: Space.sm,
      paddingVertical: Space.xs,
      borderRadius: Radius.xs,
      zIndex: 10,
    },
    errorText: {
      ...Type.compact,
      flexShrink: 1,
      color: theme.onMedia,
      textAlign: "center",
    },
    bottom: {
      position: "absolute",
      left: 0,
      right: 0,
      bottom: 0,
      zIndex: 10,
    },
    bottomScrim: {
      ...StyleSheet.absoluteFill,
      backgroundColor: withAlpha(theme.mediaScrim, 0.45),
    },
    controls: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      paddingHorizontal: Space.md,
      marginTop: Space.sm,
    },
    photosBtn: {
      width: 72,
      height: SCANNER_TOP_CONTROL_PX,
      alignItems: "center",
      justifyContent: "center",
    },
    sideControl: {
      width: 52,
      height: 52,
      borderRadius: Radius.full,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: withAlpha(theme.onMedia, 0.14),
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: withAlpha(theme.onMedia, 0.24),
    },
    sideSlot: {
      width: 72,
      height: 52,
      alignItems: "center",
      justifyContent: "center",
    },
    shutter: {
      width: SCANNER_SHUTTER_PX,
      height: SCANNER_SHUTTER_PX,
      borderRadius: Radius.full,
      borderWidth: 4,
      borderColor: theme.onMedia,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: withAlpha(theme.onMedia, 0.18),
    },
    shutterInner: {
      width: 60,
      height: 60,
      borderRadius: Radius.full,
      backgroundColor: theme.onMedia,
    },
    previewActions: {
      position: "absolute",
      left: Space.md,
      right: Space.md,
      bottom: 0,
      flexDirection: "row",
      gap: Space.sm,
      zIndex: 10,
    },
    previewSecondary: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      paddingVertical: Space.sm,
      borderRadius: Radius.md,
      backgroundColor: withAlpha(theme.onMedia, 0.18),
      minHeight: Space.minTouch,
    },
    previewSecondaryText: {
      ...Type.label,
      color: theme.onMedia,
      ...Weight.bold,
    },
    previewPrimary: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      paddingVertical: Space.sm,
      borderRadius: Radius.md,
      backgroundColor: theme.primary,
      minHeight: Space.minTouch,
    },
    previewPrimaryText: {
      ...Type.label,
      color: theme.onPrimary,
      ...Weight.bold,
    },
  });
}
