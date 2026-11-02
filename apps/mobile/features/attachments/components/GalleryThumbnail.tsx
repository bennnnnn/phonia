import { memo, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { Image } from "expo-image";

import { Icon } from "@/ui/icons/Icon";
import { MediaLoadRetry } from "@/components/MediaLoadRetry";
import { useAuthToken } from "@/contexts/AuthContext";
import { attachmentRecordExists } from "@/lib/api";
import { attachmentThumbWidth, resolveAttachmentUri } from "@/features/attachments/model/attachmentUri";
import { Theme, useTheme } from "@/lib/theme";
import { IconSize } from "@/ui/icons/sizes";
import { Radius } from "@/lib/radius";

type Props = {
  /** Attachment id — used to build the authenticated /file URL. */
  attachmentId: string;
  /** Optional already-resolved URL (presigned). Falls back to /file. */
  downloadUrl?: string | null;
  /** Square thumbnail size in px. */
  size?: number;
  /** Called once when the server confirms the record is gone (GET /url 404). */
  onMissing?: (attachmentId: string) => void;
};

const LOAD_TIMEOUT_MS = 20_000;
const RETRY_LABEL_MIN_SIZE = 80;

export { LOAD_TIMEOUT_MS };

function GalleryThumbnailBase({
  attachmentId,
  downloadUrl,
  size = 1,
  onMissing,
}: Props) {
  const C = useTheme();
  const s = useMemo(() => makeStyles(C), [C]);
  const token = useAuthToken();
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const missingNotifiedRef = useRef(false);
  const probeGenRef = useRef(0);

  // 2x for sharp tiles, capped at what the API serves (a tablet tile asks for less than 2x).
  const uri = resolveAttachmentUri({
    attachmentId,
    path: downloadUrl,
    width: attachmentThumbWidth(size * 2),
  })!;

  // resolveAttachmentUri prefers /file when attachmentId is set. That
  // endpoint always needs Bearer — including when the list also returned a
  // presigned R2 URL (ChatMessageImage sends auth the same way).
  const source = token
    ? { uri, headers: { Authorization: `Bearer ${token}` } }
    : { uri };

  const dimension = { width: size, height: size };
  const compact = size < RETRY_LABEL_MIN_SIZE;

  const onMissingRef = useRef(onMissing);
  onMissingRef.current = onMissing;
  const tokenRef = useRef(token);
  tokenRef.current = token;

  const clearLoadTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const reportMissing = () => {
    if (missingNotifiedRef.current) return;
    missingNotifiedRef.current = true;
    onMissingRef.current?.(attachmentId);
  };

  const dropIfGone = async () => {
    const auth = tokenRef.current;
    if (!auth) return;
    const gen = ++probeGenRef.current;
    const exists = await attachmentRecordExists(auth, attachmentId);
    if (gen !== probeGenRef.current) return;
    if (exists === false) reportMissing();
  };

  // Fallback: if onLoad doesn't fire within the timeout, mark as failed.
  // React Native's Image doesn't always call onError for corrupt/missing data.
  useEffect(() => {
    setFailed(false);
    setLoaded(false);
    missingNotifiedRef.current = false;
    probeGenRef.current += 1;
    clearLoadTimer();
    timerRef.current = setTimeout(() => {
      setFailed(true);
    }, LOAD_TIMEOUT_MS);
    return clearLoadTimer;
  }, [attachmentId, uri, attempt]);

  return (
    <View style={[s.wrap, dimension]}>
      {failed ? (
        <View style={[s.fallback, dimension]}>
          {compact ? null : (
            <Icon name="image" size={IconSize.md} color={C.textTertiary} />
          )}
          <MediaLoadRetry
            compact={compact}
            onRetry={() => setAttempt((n) => n + 1)}
          />
        </View>
      ) : (
        <>
          {!loaded ? (
            <View style={[s.loading, dimension]} testID="gallery-thumb-loading">
              <ActivityIndicator size="small" color={C.textTertiary} />
            </View>
          ) : null}
          <Image
            key={`${uri}:${attempt}`}
            testID="gallery-thumb-image"
            source={source}
            style={[dimension, s.image]}
            contentFit="cover"
            cachePolicy="memory-disk"
            onLoad={() => {
              clearLoadTimer();
              setLoaded(true);
            }}
            onError={() => {
              clearLoadTimer();
              setFailed(true);
              void dropIfGone();
            }}
          />
        </>
      )}
    </View>
  );
}

export const GalleryThumbnail = memo(GalleryThumbnailBase);

function makeStyles(C: Theme) {
  return StyleSheet.create({
    wrap: {
      borderRadius: Radius.sm,
      overflow: "hidden",
      backgroundColor: C.surface,
    },
    image: {
      backgroundColor: C.surface,
    },
    loading: {
      position: "absolute",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 1,
    },
    fallback: {
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: C.surface,
    },
  });
}
