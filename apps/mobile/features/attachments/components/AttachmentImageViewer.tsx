import { useEffect, useMemo, useRef, useState } from "react";
import {
  AccessibilityInfo,
  FlatList,
  Platform,
  StyleSheet,
  View,
  useWindowDimensions,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from "react-native";
import { StatusBar } from "expo-status-bar";
import { GestureDetector, GestureHandlerRootView } from "react-native-gesture-handler";
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

import { AttachmentImageStage } from "@/features/attachments/components/AttachmentImageStage";
import { AttachmentLightboxChrome } from "@/features/attachments/components/AttachmentLightboxChrome";
import { ActionFeedbackProvider, useActionFeedback } from "@/contexts/ActionFeedbackContext";
import { useAuthToken } from "@/contexts/AuthContext";
import { useSheetPanDismiss } from "@/ui/overlay/useSheetPanDismiss";
import { saveChatAttachmentToLibrary, shareChatAttachment } from "@/features/attachments/model/downloadChatAttachment";
import { resolveAttachmentUri } from "@/features/attachments/model/attachmentUri";
import {
  isNearViewerEnd,
  resolveViewerIndex,
  viewerImageKey,
  type AttachmentViewerImage,
} from "@/features/attachments/model/imageViewer";
import { useReduceMotion } from "@/lib/reduceMotion";
import { shareFailureKey } from "@/lib/shareUnavailable";
import { useTheme } from "@/lib/theme";
import { FullScreenModal } from "@/ui/overlay/FullScreenModal";

type Props = {
  visible: boolean;
  onClose: () => void;
  images?: AttachmentViewerImage[];
  initialIndex?: number;
  attachmentId?: string | null;
  localUri?: string | null;
  path?: string | null;
  fileName?: string;
  /** Already-resolved display URI from the chat thumbnail (instant open). */
  previewUri?: string | null;
  /** Open the originating chat (gallery). */
  onOpenChat?: (image: AttachmentViewerImage) => void;
  /** Attach this Library item to the composer. */
  onUseInChat?: (image: AttachmentViewerImage) => void;
  /** Remove this Library item (gallery). */
  onDelete?: (image: AttachmentViewerImage) => void;
  /** The photo on screen after the user pages (or after the one shown is deleted). */
  onIndexChange?: (image: AttachmentViewerImage, index: number) => void;
  /** Close to the last photo: the Library loads its next page. */
  onNearEnd?: () => void;
};

/**
 * The full-screen photo viewer: a black page with Close, More, Download and
 * Share on top. Swipe between photos, swipe down to close, pinch or double
 * tap to zoom, tap to hide the controls. Its toasts show inside it.
 */
export function AttachmentImageViewer(props: Props) {
  const { visible, onClose } = props;
  const modalVisible = useLightStatusBarFirst(visible);
  // Each opening starts fresh (page, zoom, controls), even when iOS reopens
  // the modal before the previous close finished.
  const [session, setSession] = useState(0);
  const [wasVisible, setWasVisible] = useState(visible);
  if (visible !== wasVisible) {
    setWasVisible(visible);
    if (visible) setSession((n) => n + 1);
  }

  return (
    <>
      {visible ? <StatusBar style="light" /> : null}
      <FullScreenModal
        visible={modalVisible}
        transparent
        animationType="fade"
        presentationStyle="overFullScreen"
        statusBarTranslucent
        onRequestClose={onClose}
      >
        <GestureHandlerRootView style={s.flex}>
          <ActionFeedbackProvider appearance="media">
            <ViewerContent key={session} {...props} />
          </ActionFeedbackProvider>
        </GestureHandlerRootView>
      </FullScreenModal>
    </>
  );
}

/**
 * Android's modal copies the status bar look from the screen when it opens,
 * so turn the bar light first and open the modal on the next frame.
 */
function useLightStatusBarFirst(visible: boolean): boolean {
  const waitForBar = Platform.OS === "android";
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!visible || !waitForBar) {
      setReady(false);
      return;
    }
    const frame = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(frame);
  }, [visible, waitForBar]);
  return waitForBar ? visible && ready : visible;
}

function ViewerContent({
  onClose,
  images,
  initialIndex = 0,
  attachmentId,
  localUri,
  path,
  fileName = "image.jpg",
  previewUri = null,
  onOpenChat,
  onUseInChat,
  onDelete,
  onIndexChange,
  onNearEnd,
}: Props) {
  const { t } = useTranslation();
  const token = useAuthToken();
  const feedback = useActionFeedback();
  const insets = useSafeAreaInsets();
  const theme = useTheme();
  const { width: screenWidth } = useWindowDimensions();
  const reduceMotion = useReduceMotion();
  const [zoomed, setZoomed] = useState(false);
  // A zoomed photo owns the drag: swipe-down-to-close and paging wait for 1x.
  const { pan, translateY } = useSheetPanDismiss(!zoomed, reduceMotion, onClose);
  // Fade/scale-in entrance (the Modal fade covers opacity; this adds the
  // scale). Reduce Motion skips it — content appears at final scale.
  const entrance = useSharedValue(reduceMotion ? 1 : 0);
  const [busy, setBusy] = useState<"download" | "share" | null>(null);
  const [chromeVisible, setChromeVisible] = useState(true);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const pagerRef = useRef<FlatList<AttachmentViewerImage>>(null);

  const items = useMemo((): AttachmentViewerImage[] => {
    if (images && images.length > 0) return images;
    return [{ attachmentId, localUri, path, fileName, previewUri }];
  }, [images, attachmentId, localUri, path, fileName, previewUri]);

  // Follow the photo by identity, not position: deleting a photo or loading
  // the next Library page must not change which photo the actions act on.
  const [current, setCurrent] = useState(() => {
    const index = Math.min(Math.max(0, initialIndex), Math.max(0, items.length - 1));
    return { key: viewerImageKey(items[index]), index };
  });
  const pageIndex = resolveViewerIndex(items, current.key, current.index);
  const currentItem = items[pageIndex] ?? items[0];
  const currentKey = viewerImageKey(currentItem);
  if (currentKey !== current.key || pageIndex !== current.index) {
    setCurrent({ key: currentKey, index: pageIndex });
  }
  const scrolledRef = useRef({ index: pageIndex, width: screenWidth });

  /* eslint-disable react-hooks/immutability -- Reanimated shared values are set from effects. */
  useEffect(() => {
    translateY.value = 0;
    if (reduceMotion) {
      entrance.value = 1;
      return;
    }
    entrance.value = withTiming(1, {
      duration: 220,
      easing: Easing.out(Easing.cubic),
    });
  }, [reduceMotion, translateY, entrance]);
  /* eslint-enable react-hooks/immutability */

  // Keep the pager on the current photo when photos before it come or go.
  useEffect(() => {
    const scrolled = scrolledRef.current;
    if (scrolled.index === pageIndex && scrolled.width === screenWidth) return;
    scrolledRef.current = { index: pageIndex, width: screenWidth };
    if (items.length > 1) {
      pagerRef.current?.scrollToOffset({ offset: pageIndex * screenWidth, animated: false });
    }
  }, [pageIndex, screenWidth, items.length]);

  // Tell the owner and the screen reader which photo is showing now.
  const label = (item: AttachmentViewerImage | undefined, index: number) => {
    const name = item?.label ?? item?.fileName ?? fileName;
    return items.length > 1
      ? t("gallery.viewer_image_a11y", { name, index: index + 1, count: items.length })
      : name;
  };
  const currentLabel = label(currentItem, pageIndex);
  const reportedKeyRef = useRef(currentKey);
  useEffect(() => {
    if (reportedKeyRef.current === currentKey) return;
    reportedKeyRef.current = currentKey;
    setZoomed(false);
    if (currentItem) onIndexChange?.(currentItem, pageIndex);
    AccessibilityInfo.announceForAccessibility(currentLabel);
  }, [currentKey, currentItem, pageIndex, onIndexChange, currentLabel]);

  useEffect(() => {
    if (onNearEnd && isNearViewerEnd(pageIndex, items.length)) onNearEnd();
  }, [pageIndex, items.length, onNearEnd]);

  // Single animated style: panStyle's transform would override a separate
  // entrance transform, so compose translateY + scale in one place.
  const rootAnimatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: translateY.value },
      { scale: 0.94 + 0.06 * entrance.value },
    ],
  }));

  const remoteUri = resolveAttachmentUri({
    attachmentId: currentItem?.attachmentId,
    localUri: currentItem?.localUri,
    path: currentItem?.path,
  });
  const currentName = currentItem?.fileName ?? fileName;
  const showUseInChat = Boolean(onUseInChat && currentItem);
  const showOpenChat = Boolean(onOpenChat && currentItem?.chatId);
  const showDelete = Boolean(onDelete && currentItem);

  const handleDownload = async () => {
    if (!remoteUri || busy) return;
    setBusy("download");
    try {
      const result = await saveChatAttachmentToLibrary({
        uri: remoteUri,
        token,
        fileName: currentName,
      });
      if (result === "saved") feedback.success(t("common.saved_to_photos"));
    } catch (error) {
      // Photos refused falls back to the share sheet, which an old build may not have.
      feedback.error(t(shareFailureKey(error, "common.download_image_error")));
    } finally {
      setBusy(null);
    }
  };

  const handleShare = async () => {
    if (!remoteUri || busy) return;
    setBusy("share");
    try {
      await shareChatAttachment({
        uri: remoteUri,
        token,
        fileName: currentName,
      });
    } catch (error) {
      feedback.error(t(shareFailureKey(error, "common.share_image_error")));
    } finally {
      setBusy(null);
    }
  };

  const onPageScrollEnd = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const next = Math.round(event.nativeEvent.contentOffset.x / screenWidth);
    if (next < 0 || next >= items.length) return;
    scrolledRef.current = { index: next, width: screenWidth };
    if (next !== pageIndex) setCurrent({ key: viewerImageKey(items[next]), index: next });
  };

  const onImagePress = () => {
    if (overflowOpen) {
      setOverflowOpen(false);
      return;
    }
    setChromeVisible((open) => !open);
  };

  const stage = (item: AttachmentViewerImage, index: number, active: boolean) => (
    <AttachmentImageStage
      item={item}
      active={active}
      onPress={onImagePress}
      onZoomChange={index === pageIndex ? setZoomed : undefined}
      accessibilityLabel={label(item, index)}
    />
  );

  const runOnCurrent = (action: ((image: AttachmentViewerImage) => void) | undefined) => {
    if (!currentItem || !action) return;
    setOverflowOpen(false);
    action(currentItem);
  };

  return (
    <GestureDetector gesture={pan}>
      <Animated.View
        testID="attachment-image-viewer"
        collapsable={false}
        style={[s.root, { backgroundColor: theme.mediaScrim }, rootAnimatedStyle]}
      >
        {items.length > 1 ? (
          <FlatList
            ref={pagerRef}
            testID="attachment-viewer-pager"
            style={s.pager}
            data={items}
            horizontal
            pagingEnabled
            scrollEnabled={!zoomed}
            nestedScrollEnabled
            showsHorizontalScrollIndicator={false}
            keyExtractor={(item, index) => viewerImageKey(item) ?? `img-${index}`}
            getItemLayout={(_, index) => ({
              length: screenWidth,
              offset: screenWidth * index,
              index,
            })}
            initialScrollIndex={scrolledRef.current.index}
            onScrollToIndexFailed={() => undefined}
            onMomentumScrollEnd={onPageScrollEnd}
            renderItem={({ item, index }) =>
              // FlatList keeps up to 21 pages mounted and the Library passes
              // every loaded photo. Only the photo on screen and its
              // neighbours download and decode; the rest hold their width.
              Math.abs(index - pageIndex) <= 1 ? (
                <View style={{ width: screenWidth, height: "100%" }}>
                  {stage(item, index, true)}
                </View>
              ) : (
                <View
                  style={{ width: screenWidth, height: "100%" }}
                  testID="attachment-viewer-page-placeholder"
                />
              )
            }
          />
        ) : (
          stage(items[0] ?? { previewUri }, 0, true)
        )}

        <AttachmentLightboxChrome
          visible={chromeVisible}
          overflowOpen={overflowOpen}
          insets={insets}
          busy={busy}
          canShare={Boolean(remoteUri)}
          showUseInChat={showUseInChat}
          showOpenChat={showOpenChat}
          showDelete={showDelete}
          onClose={onClose}
          onShare={() => void handleShare()}
          onDownload={() => void handleDownload()}
          onToggleOverflow={() => setOverflowOpen((open) => !open)}
          onCloseOverflow={() => setOverflowOpen(false)}
          onUseInChat={() => runOnCurrent(onUseInChat)}
          onOpenChat={() => runOnCurrent(onOpenChat)}
          onDelete={() => runOnCurrent(onDelete)}
        />
      </Animated.View>
    </GestureDetector>
  );
}

const s = StyleSheet.create({
  flex: {
    flex: 1,
  },
  root: {
    flex: 1,
  },
  pager: {
    flex: 1,
  },
});
