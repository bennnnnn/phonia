/* eslint-disable react-hooks/immutability -- Reanimated shared values mutate `.value` in gestures and effects. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Image, type ImageLoadEventData } from "expo-image";
import {
  ActivityIndicator,
  Image as ReactNativeImage,
  StyleSheet,
  View,
  type AccessibilityActionEvent,
} from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withDecay,
  withSpring,
} from "react-native-reanimated";

import { MediaLoadRetry } from "@/components/MediaLoadRetry";
import { useAuthToken } from "@/contexts/AuthContext";
import { useAccountSession } from "@/contexts/accountSession";
import {
  ensureLocalAttachmentFile,
  getCachedAttachmentFile,
  invalidateCachedAttachmentFile,
} from "@/features/attachments/model/downloadChatAttachment";
import { resolveAttachmentUri, attachmentRequestHeaders } from "@/features/attachments/model/attachmentUri";
import type { AttachmentViewerImage } from "@/features/attachments/model/imageViewer";
import {
  clampPan,
  doubleTapZoom,
  focalOffset,
  isZoomed,
  maxPan,
  pinchScale,
} from "@/features/attachments/model/imageZoom";
import { getSessionGeneration } from "@/lib/auth";
import { fitImageToStage } from "@/lib/fitImageToStage";
import { useReduceMotion } from "@/lib/reduceMotion";
import { useTheme } from "@/lib/theme";

/** Settles without bounce, so a released photo never shows the stage edge. */
const ZOOM_SPRING = { damping: 30, stiffness: 300, overshootClamping: true } as const;
/** Long enough to tell a double tap from a tap, short enough that a tap feels immediate. */
const DOUBLE_TAP_DELAY_MS = 250;

type Props = {
  item: AttachmentViewerImage;
  active: boolean;
  /** A single tap (shows or hides the viewer's controls). */
  onPress?: () => void;
  /** Called when the photo zooms past 1x and when it returns to 1x. */
  onZoomChange?: (zoomed: boolean) => void;
  /** What a screen reader says for the photo (its name and place in the set). */
  accessibilityLabel?: string;
};

/**
 * One photo in the viewer. Pinch or double tap zooms it; while zoomed, one
 * finger pans within the photo, and a double tap or pinching out resets it.
 */
export function AttachmentImageStage({ item, active, onPress, onZoomChange, accessibilityLabel }: Props) {
  const token = useAuthToken();
  const { account, getToken } = useAccountSession();
  const reduceMotion = useReduceMotion();
  const theme = useTheme();
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [cachedFile, setCachedFile] = useState<{ key: object; uri: string } | null>(null);
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null);
  const [stage, setStage] = useState({ width: 0, height: 0 });
  const [zoomed, setZoomed] = useState(false);

  const fileName = item.fileName ?? "image.jpg";
  const remoteUri = useMemo(() => {
    return resolveAttachmentUri({
      attachmentId: item.attachmentId,
      localUri: item.localUri,
      path: item.path,
    });
  }, [item.attachmentId, item.localUri, item.path]);

  const sessionGeneration = getSessionGeneration();
  const fileKey = useMemo(() => ({ remoteUri, sessionGeneration }), [remoteUri, sessionGeneration]);
  const cachedUri = cachedFile?.key === fileKey ? cachedFile.uri : null;

  const displayUri =
    cachedUri ||
    (remoteUri ? getCachedAttachmentFile(remoteUri) : null) ||
    item.localUri ||
    item.previewUri ||
    remoteUri;

  const fitted =
    natural && stage.width > 0 && stage.height > 0
      ? fitImageToStage(natural.width, natural.height, stage.width, stage.height)
      : null;

  // Zoom state lives on the UI thread; the sizes it is clamped to come from layout.
  const scale = useSharedValue(1);
  const offsetX = useSharedValue(0);
  const offsetY = useSharedValue(0);
  const startScale = useSharedValue(1);
  const startX = useSharedValue(0);
  const startY = useSharedValue(0);
  const focalX = useSharedValue(0);
  const focalY = useSharedValue(0);
  const zoomedOnUi = useSharedValue(false);
  const stageW = useSharedValue(0);
  const stageH = useSharedValue(0);
  const contentW = useSharedValue(0);
  const contentH = useSharedValue(0);

  useEffect(() => {
    stageW.value = stage.width;
    stageH.value = stage.height;
    contentW.value = fitted?.width ?? stage.width;
    contentH.value = fitted?.height ?? stage.height;
  }, [stage.width, stage.height, fitted?.width, fitted?.height, stageW, stageH, contentW, contentH]);

  // Gestures call back through refs, so a parent re-render does not rebuild them mid-pinch.
  const onPressRef = useRef(onPress);
  onPressRef.current = onPress;
  const onZoomChangeRef = useRef(onZoomChange);
  onZoomChangeRef.current = onZoomChange;
  const firePress = useCallback(() => onPressRef.current?.(), []);
  const reportZoom = useCallback((next: boolean) => {
    setZoomed(next);
    onZoomChangeRef.current?.(next);
  }, []);

  // Paging away or showing another photo starts it at 1x again.
  useEffect(() => {
    scale.value = 1;
    offsetX.value = 0;
    offsetY.value = 0;
    if (zoomedOnUi.value) {
      zoomedOnUi.value = false;
      reportZoom(false);
    }
  }, [active, remoteUri, scale, offsetX, offsetY, zoomedOnUi, reportZoom]);

  const gesture = useMemo(() => {
    const syncZoomed = (next: boolean) => {
      "worklet";
      if (next === zoomedOnUi.value) return;
      zoomedOnUi.value = next;
      runOnJS(reportZoom)(next);
    };
    const settle = (to: number, x: number, y: number) => {
      "worklet";
      scale.value = reduceMotion ? to : withSpring(to, ZOOM_SPRING);
      offsetX.value = reduceMotion ? x : withSpring(x, ZOOM_SPRING);
      offsetY.value = reduceMotion ? y : withSpring(y, ZOOM_SPRING);
      syncZoomed(isZoomed(to));
    };

    const pinch = Gesture.Pinch()
      .onStart((event) => {
        startScale.value = scale.value;
        startX.value = offsetX.value;
        startY.value = offsetY.value;
        focalX.value = event.focalX - stageW.value / 2;
        focalY.value = event.focalY - stageH.value / 2;
        syncZoomed(true);
      })
      .onUpdate((event) => {
        const next = pinchScale(startScale.value, event.scale);
        scale.value = next;
        offsetX.value = focalOffset(startX.value, focalX.value, event.focalX - stageW.value / 2, startScale.value, next);
        offsetY.value = focalOffset(startY.value, focalY.value, event.focalY - stageH.value / 2, startScale.value, next);
      })
      .onEnd(() => {
        if (!isZoomed(scale.value)) {
          settle(1, 0, 0);
          return;
        }
        const to = scale.value;
        settle(
          to,
          clampPan(offsetX.value, contentW.value, stageW.value, to),
          clampPan(offsetY.value, contentH.value, stageH.value, to),
        );
      });

    // One finger moves a zoomed photo; at 1x the pager and swipe-to-close own the drag.
    const pan = Gesture.Pan()
      .enabled(zoomed)
      .maxPointers(1)
      .onStart(() => {
        startX.value = offsetX.value;
        startY.value = offsetY.value;
      })
      .onUpdate((event) => {
        offsetX.value = clampPan(startX.value + event.translationX, contentW.value, stageW.value, scale.value);
        offsetY.value = clampPan(startY.value + event.translationY, contentH.value, stageH.value, scale.value);
      })
      .onEnd((event) => {
        if (reduceMotion) return;
        const limitX = maxPan(contentW.value, stageW.value, scale.value);
        const limitY = maxPan(contentH.value, stageH.value, scale.value);
        offsetX.value = withDecay({ velocity: event.velocityX, clamp: [-limitX, limitX] });
        offsetY.value = withDecay({ velocity: event.velocityY, clamp: [-limitY, limitY] });
      });

    const doubleTap = Gesture.Tap()
      .numberOfTaps(2)
      .maxDelay(DOUBLE_TAP_DELAY_MS)
      .onEnd((event, success) => {
        if (!success) return;
        const target = doubleTapZoom(
          scale.value,
          event.x - stageW.value / 2,
          event.y - stageH.value / 2,
          { width: contentW.value, height: contentH.value },
          { width: stageW.value, height: stageH.value },
        );
        settle(target.scale, target.x, target.y);
      });

    const singleTap = Gesture.Tap()
      .numberOfTaps(1)
      .onEnd((_event, success) => {
        if (success) runOnJS(firePress)();
      });

    return Gesture.Simultaneous(Gesture.Simultaneous(pinch, pan), Gesture.Exclusive(doubleTap, singleTap));
  }, [
    zoomed,
    reduceMotion,
    firePress,
    reportZoom,
    scale,
    offsetX,
    offsetY,
    startScale,
    startX,
    startY,
    focalX,
    focalY,
    zoomedOnUi,
    stageW,
    stageH,
    contentW,
    contentH,
  ]);

  const zoomStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: offsetX.value },
      { translateY: offsetY.value },
      { scale: scale.value },
    ],
  }));

  useEffect(() => {
    setNatural(null);
  }, [remoteUri, item.localUri, item.previewUri]);

  useEffect(() => {
    if (!active) return;
    setFailed(false);
    if (!remoteUri && !item.localUri && !item.previewUri) {
      setFailed(true);
      return;
    }
    if (!remoteUri) return;

    // Leaving this photo stops its download unless Share or another view still waits.
    const controller = new AbortController();
    void ensureLocalAttachmentFile({
      uri: remoteUri,
      token: getToken(),
      fileName,
      signal: controller.signal,
    })
      .then((uri) => {
        if (!controller.signal.aborted) setCachedFile({ key: fileKey, uri });
      })
      .catch(() => {
        // Keep showing previewUri / remote; download/share will surface errors.
      });
    return () => controller.abort();
  }, [active, remoteUri, item.localUri, item.previewUri, account, getToken, fileName, attempt, fileKey]);

  useEffect(() => {
    const uri = cachedUri ?? (item.localUri?.startsWith("file://") ? item.localUri : null);
    if (!uri) return;
    let cancelled = false;
    ReactNativeImage.getSize(
      uri,
      (width, height) => {
        if (!cancelled && width > 0 && height > 0) setNatural({ width, height });
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [cachedUri, item.localUri]);

  const source = useMemo(() => {
    if (!displayUri) return null;
    const headers = attachmentRequestHeaders(displayUri, token);
    if (!Object.keys(headers).length) return { uri: displayUri };
    return {
      uri: displayUri,
      headers,
      // Authenticated attachment URLs can be identical across accounts.
      // Scope expo-image's disk cache to the current session, and let Retry
      // bypass a possibly corrupt cached response without leaking file keys.
      cacheKey: `attachment:${sessionGeneration}:${attempt}:${displayUri}`,
    };
  }, [attempt, displayUri, sessionGeneration, token]);

  const handleLoad = (event: ImageLoadEventData) => {
    const { width, height } = event.source;
    if (
      Number.isFinite(width) &&
      Number.isFinite(height) &&
      width > 0 &&
      height > 0
    ) {
      setNatural({ width, height });
    }
  };

  // Screen readers cannot double tap to zoom; activating the photo toggles the controls.
  const onAccessibilityAction = (event: AccessibilityActionEvent) => {
    if (event.nativeEvent.actionName === "activate") onPress?.();
  };

  if (failed) {
    return (
      <View style={s.stage}>
        <MediaLoadRetry
          media
          onRetry={() => {
            if (remoteUri) invalidateCachedAttachmentFile(remoteUri);
            setCachedFile(null);
            setFailed(false);
            setAttempt((n) => n + 1);
          }}
        />
      </View>
    );
  }

  if (!source) {
    return (
      <View style={s.stage}>
        <ActivityIndicator color={theme.onMedia} size="large" />
      </View>
    );
  }

  return (
    <GestureDetector gesture={gesture}>
      <View
        style={s.stage}
        collapsable={false}
        testID="attachment-viewer-tap"
        accessible
        accessibilityRole="image"
        accessibilityLabel={accessibilityLabel ?? item.label ?? fileName}
        accessibilityActions={onPress ? [{ name: "activate" }] : undefined}
        onAccessibilityAction={onAccessibilityAction}
        onLayout={(event) => {
          const { width, height } = event.nativeEvent.layout;
          setStage((prev) =>
            prev.width === width && prev.height === height ? prev : { width, height },
          );
        }}
      >
        <Animated.View style={[fitted ?? s.imageFill, zoomStyle]} testID="attachment-viewer-zoom">
          <Image
            key={`${displayUri}:${attempt}`}
            testID="attachment-viewer-image"
            source={source}
            style={fitted ?? s.imageFill}
            contentFit="contain"
            cachePolicy="memory-disk"
            onLoad={handleLoad}
            onError={() => setFailed(true)}
          />
        </Animated.View>
      </View>
    </GestureDetector>
  );
}

const s = StyleSheet.create({
  stage: {
    flex: 1,
    width: "100%",
    alignItems: "center",
    justifyContent: "center",
  },
  imageFill: {
    width: "100%",
    height: "100%",
  },
});
