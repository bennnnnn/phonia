import { useEffect, useMemo, useRef, useState } from "react";
import {
  Pressable,
  StyleSheet,
  useWindowDimensions,
  View,
} from "react-native";
import { Image, type ImageLoadEventData, type ImageSource } from "expo-image";
import { useTranslation } from "react-i18next";
import Animated, { Easing, useAnimatedStyle, useSharedValue, withTiming } from "react-native-reanimated";

import { MediaLoadRetry } from "@/components/MediaLoadRetry";
import { LazyAttachmentImageViewer } from "@/features/attachments/components/LazyAttachmentImageViewer";
import { useAuthToken } from "@/contexts/AuthContext";
import { resolveAttachmentUri, attachmentRequestHeaders } from "@/features/attachments/model/attachmentUri";
import { fitAttachmentImage, type ImageSize } from "@/features/attachments/model/attachmentImageSize";
import { motionMs, useReduceMotion } from "@/lib/motion";
import { Theme, useTheme } from "@/lib/theme";
import { Radius } from "@/lib/radius";

const AnimatedImage = Animated.createAnimatedComponent(Image);
const REVEAL_DURATION_MS = 280;
const REVEAL_BLUR_RADIUS = 16;

type Props = {
  attachmentId?: string | null;
  localUri?: string | null;
  path?: string | null;
  fileName?: string;
  /**
   * Soft blur→sharp "develop" reveal. Default on for generated/assistant
   * images; user attach previews should pass false so a post-reply refetch
   * doesn't flash gray/blur again.
   */
  animatedReveal?: boolean;
  /** Show the complete user attachment instead of cropping its contents. */
  previewFit?: "cover" | "contain";
  /** Override the default ~1/3-screen thumb. Used by the multi-image strip. */
  width?: number;
  height?: number;
  /** If set, tap opens this instead of the built-in single-image viewer. */
  onOpen?: () => void;
};

/** ~1/3 screen width, slightly portrait — matches Claude-style chat thumbnails. */
export function useThumbnailSize() {
  const { width: screenWidth } = useWindowDimensions();
  const width = Math.round(Math.min(screenWidth * 0.34, 148));
  const height = Math.round(width * 1.28);
  return { width, height };
}

type RevealingImageProps = {
  source: ImageSource;
  style: ReturnType<typeof makeStyles>["preview"];
  layerStyle: ReturnType<typeof makeStyles>["layer"];
  onError: () => void;
  onLoad: (event: ImageLoadEventData) => void;
  reduceMotion: boolean;
  previewFit: "cover" | "contain";
};

/** Owns the blur→sharp reveal animation for one image load. Keyed by URI at
 * the call site so a different image gets a fresh shared value on mount
 * instead of an imperative reset. */
function RevealingImage({
  source,
  style,
  layerStyle,
  onError,
  onLoad,
  reduceMotion,
  previewFit,
}: RevealingImageProps) {
  const reveal = useSharedValue(reduceMotion ? 1 : 0);
  const started = useRef(false);
  const sharpStyle = useAnimatedStyle(() => ({ opacity: reveal.value }));
  const blurStyle = useAnimatedStyle(() => ({ opacity: 1 - reveal.value }));

  const handleLoad = (event: ImageLoadEventData) => {
    if (started.current) return;
    started.current = true;
    onLoad(event);
    // Reanimated shared values are designed to be mutated from any JS-thread
    // callback, including a plain event handler like this one — this isn't
    // the kind of render-purity violation the immutability rule exists to
    // catch. The rule doesn't yet recognize SharedValue as an exempt
    // mutable-ref type (a known gap for Reanimated under React Compiler).
    // eslint-disable-next-line react-hooks/immutability -- a shared value written in an event handler, not in render
    reveal.value = withTiming(1, {
      duration: motionMs(REVEAL_DURATION_MS, reduceMotion),
      easing: Easing.out(Easing.ease),
    });
  };

  if (reduceMotion) {
    return (
      <AnimatedImage
        source={source}
        style={[style, layerStyle]}
        contentFit={previewFit}
        cachePolicy="memory-disk"
        onError={onError}
        onLoad={onLoad}
      />
    );
  }

  return (
    <>
      {/* Blurred layer fades out as the sharp layer fades in — a soft
          "develop" reveal rather than a hard pop once decoded. */}
      <AnimatedImage
        source={source}
        style={[style, layerStyle, blurStyle]}
        contentFit={previewFit}
        cachePolicy="memory-disk"
        blurRadius={REVEAL_BLUR_RADIUS}
        onLoad={handleLoad}
      />
      <AnimatedImage
        source={source}
        style={[style, layerStyle, sharpStyle]}
        contentFit={previewFit}
        cachePolicy="memory-disk"
        onLoad={handleLoad}
        onError={onError}
      />
    </>
  );
}

export function ChatMessageImage(props: Props) {
  // Request a server-resized thumb (?w=) at 2× the layout width — pulling the
  // full-resolution original into a ~148px bubble wastes decode time and data.
  const thumb = useThumbnailSize();
  const maxWidth = props.width ?? thumb.width;
  const uri = resolveAttachmentUri({
    attachmentId: props.attachmentId,
    localUri: props.localUri,
    path: props.path,
    width: Math.round(maxWidth * 2),
  });
  if (!uri) return null;
  // A new source owns new load/error state; a late event from the old image
  // cannot resize the next attachment, including local-to-remote replacement.
  return <ChatMessageImageContent key={props.localUri || uri} {...props} remoteUri={uri} />;
}

function ChatMessageImageContent({
  attachmentId,
  localUri,
  path,
  fileName,
  animatedReveal = true,
  previewFit = "cover",
  width: widthOverride,
  height: heightOverride,
  onOpen,
  remoteUri,
}: Props & { remoteUri: string }) {
  const { t } = useTranslation();
  const token = useAuthToken();
  const C = useTheme();
  const reduceMotion = useReduceMotion();
  const thumb = useThumbnailSize();
  const maxWidth = widthOverride ?? thumb.width;
  const maxHeight = heightOverride ?? thumb.height;
  const [decodedSize, setDecodedSize] = useState<ImageSize | null>(null);
  const fitted = previewFit === "contain" && decodedSize
    ? fitAttachmentImage(decodedSize, { width: maxWidth, height: maxHeight })
    : null;
  const { width, height } = fitted ?? { width: maxWidth, height: maxHeight };
  const onLoad = (event: ImageLoadEventData) => {
    if (previewFit !== "contain") return;
    const size = event.source;
    if (fitAttachmentImage(size, { width: maxWidth, height: maxHeight })) {
      setDecodedSize({ width: size.width, height: size.height });
    }
  };
  const s = useMemo(() => makeStyles(C, width, height), [C, width, height]);
  const [failed, setFailed] = useState(false);
  // Each Retry loads the photo afresh: a failure offline stayed broken until the row remounted.
  const [attempt, setAttempt] = useState(0);
  const [viewerOpen, setViewerOpen] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [remoteUri, token]);

  if (!remoteUri) return null;

  const headers = attachmentRequestHeaders(remoteUri, token);
  const source = Object.keys(headers).length ? { uri: remoteUri, headers } : { uri: remoteUri };

  // Local file:// previews (and user attach thumbs) stay sharp — no blur
  // "develop" reveal that restarts when a silent refetch swaps the URI.
  const usePlainPreview = Boolean(localUri) || !animatedReveal;
  const retry = () => {
    setFailed(false);
    setAttempt((n) => n + 1);
  };

  return (
    <>
      <Pressable
        onPress={() => {
          if (onOpen) {
            onOpen();
            return;
          }
          setViewerOpen(true);
        }}
        accessibilityLabel={t(failed ? "chat.image_unavailable_a11y" : "chat.image_view_a11y")}
        accessibilityRole="button"
        // VoiceOver reads the frame as one button, so the Retry inside it is an action.
        accessibilityActions={failed ? [{ name: "retry", label: t("common.retry") }] : undefined}
        onAccessibilityAction={(event) => {
          if (event.nativeEvent.actionName === "retry") retry();
        }}
      >
        <View style={s.wrap} testID="chat-image-frame">
          {failed ? (
            // Retry, never a spinner (that read as "still generating" when the
            // attachment 404'd). The rest of the frame still opens the viewer.
            <View style={[s.preview, s.fallback]}>
              <MediaLoadRetry onRetry={retry} />
            </View>
          ) : usePlainPreview ? (
            <Image
              key={attempt}
              source={localUri ? { uri: localUri } : source}
              style={s.preview}
              contentFit={previewFit}
              cachePolicy="memory-disk"
              onError={() => setFailed(true)}
              onLoad={onLoad}
              testID="chat-image-preview"
            />
          ) : (
            <RevealingImage
              key={`${remoteUri}#${attempt}`}
              source={source}
              style={s.preview}
              layerStyle={s.layer}
              onError={() => setFailed(true)}
              reduceMotion={reduceMotion}
              previewFit={previewFit}
              onLoad={onLoad}
            />
          )}
        </View>
      </Pressable>

      {onOpen ? null : (
        <LazyAttachmentImageViewer
          visible={viewerOpen}
          onClose={() => setViewerOpen(false)}
          attachmentId={attachmentId}
          localUri={localUri}
          path={path}
          fileName={fileName}
          previewUri={remoteUri}
        />
      )}
    </>
  );
}

function makeStyles(C: Theme, width: number, height: number) {
  return StyleSheet.create({
    wrap: {
      width,
      height,
      // The bubble's curve, so text, photo and file in one message match.
      borderRadius: Radius.bubble,
      overflow: "hidden",
      backgroundColor: C.surfaceAlt,
    },
    preview: {
      width: "100%",
      height: "100%",
    },
    layer: {
      position: "absolute",
      top: 0,
      left: 0,
    },
    fallback: {
      alignItems: "center",
      justifyContent: "center",
    },
  });
}
