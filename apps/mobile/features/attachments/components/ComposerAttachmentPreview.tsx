import { useMemo, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { Image, type ImageLoadEventData } from "expo-image";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import type { PendingAttachment } from "@/features/attachments/model/attachments";
import { fitAttachmentImage, type ImageSize } from "@/features/attachments/model/attachmentImageSize";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { IconSize } from "@/ui/icons/sizes";

// Mirror the rendered preview sizes instead of under-reserving the thread.
const IMAGE_PREVIEW_EXTRA = 120;
const FILE_PREVIEW_EXTRA = 56;

/** How much taller the composer is while this preview shows. */
export function composerAttachmentExtra(attachment: PendingAttachment | null): number {
  if (!attachment) return 0;
  return attachment.kind === "image" ? IMAGE_PREVIEW_EXTRA : FILE_PREVIEW_EXTRA;
}

type Props = {
  attachment: PendingAttachment;
  uploading?: boolean;
  onRemove: () => void;
};

export function ComposerAttachmentPreview({ attachment, uploading, onRemove }: Props) {
  const C = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(C), [C]);

  if (attachment.kind === "image") {
    return <ComposerImagePreview key={attachment.localUri} {...{ attachment, uploading, onRemove }} />;
  }

  return (
    <View
      style={s.fileWrap}
      accessibilityLabel={uploading ? t("chat.sending") : undefined}
      accessibilityState={{ busy: Boolean(uploading) }}
    >
      <View style={s.fileIcon}>
        <Icon name="file" size={IconSize.sm} color={C.primary} />
      </View>
      <Text style={s.fileName} numberOfLines={1}>
        {attachment.fileName}
      </Text>
      {uploading ? (
        <ActivityIndicator size="small" color={C.primary} />
      ) : (
        <Pressable
          onPress={onRemove}
          hitSlop={13}
          accessibilityRole="button"
          accessibilityLabel={t("chat.remove_attachment_a11y")}
        >
          <Icon name="close-circle" size={IconSize.sm} color={C.textTertiary} />
        </Pressable>
      )}
    </View>
  );
}

function ComposerImagePreview({ attachment, uploading, onRemove }: Props) {
  const C = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(C), [C]);
  const bounds = { width: 88, height: 112 };
  const [decodedSize, setDecodedSize] = useState<ImageSize | null>(null);
  const size = (decodedSize && fitAttachmentImage(decodedSize, bounds)) || bounds;
  const onLoad = (event: ImageLoadEventData) => {
    const loaded = event.source;
    if (fitAttachmentImage(loaded, bounds)) {
      setDecodedSize({ width: loaded.width, height: loaded.height });
    }
  };
  return (
    <View
      style={[s.imageControls, { width: Math.max(size.width, 44), height: Math.max(size.height, 44) }]}
      accessibilityLabel={uploading ? t("chat.sending") : undefined}
      accessibilityState={{ busy: Boolean(uploading) }}
      testID="composer-image-controls"
    >
      <View style={[s.imageWrap, size]} testID="composer-image-frame">
        <Image
          source={{ uri: attachment.localUri }}
          style={s.image}
          contentFit="contain"
          cachePolicy="memory-disk"
          onLoad={onLoad}
          testID="composer-image-preview"
        />
        {uploading ? (
          <View style={s.uploadOverlay}>
            <ActivityIndicator color={C.onMedia} />
          </View>
        ) : null}
      </View>
      <Pressable
        style={s.removeBtn}
        onPress={onRemove}
        accessibilityRole="button"
        accessibilityLabel={t("chat.remove_attachment_a11y")}
        disabled={uploading}
      >
        <View style={s.removeBtnCircle}>
          <Icon name="close" size={IconSize.xxs} color={C.text} />
        </View>
      </Pressable>
    </View>
  );
}

function makeStyles(C: Theme) {
  return StyleSheet.create({
    imageControls: {
      marginBottom: Space.xs,
    },
    imageWrap: {
      borderRadius: Radius.bubble,
      overflow: "hidden",
      backgroundColor: C.surfaceAlt,
    },
    image: {
      width: "100%",
      height: "100%",
    },
    uploadOverlay: {
      ...StyleSheet.absoluteFill,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: C.scrim,
    },
    removeBtn: {
      position: "absolute",
      // 44×44 touch target; the visible 22px circle keeps its old center
      // (top/right 4 + 11) via the negative offsets.
      top: -7,
      right: -7,
      width: 44,
      height: 44,
      alignItems: "center",
      justifyContent: "center",
    },
    removeBtnCircle: {
      width: 22,
      height: 22,
      borderRadius: Radius.full,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: C.bg,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: C.border,
    },
    fileWrap: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      marginBottom: Space.xs,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.xs,
      borderRadius: Radius.md,
      backgroundColor: C.surfaceAlt,
    },
    fileIcon: {
      width: 32,
      height: 32,
      borderRadius: Radius.xs,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: C.primaryLight,
    },
    fileName: {
      flex: 1,
      ...Type.compact,
      color: C.textSecondary,
    },
  });
}
