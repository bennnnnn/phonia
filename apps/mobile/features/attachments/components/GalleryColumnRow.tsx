import { useMemo } from "react";
import { StyleSheet, View, type AccessibilityActionEvent, type AccessibilityActionInfo } from "react-native";

import { GalleryThumbnail } from "@/features/attachments/components/GalleryThumbnail";
import { Icon } from "@/ui/icons/Icon";
import { ListRow } from "@/ui/list/ListRow";
import { type AttachmentListItem } from "@/lib/api";
import { COLUMN_THUMB_SIZE, isGalleryImage } from "@/features/attachments/model/gallery";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Radius } from "@/lib/radius";
import { IconSize } from "@/ui/icons/sizes";

/** Where a column row's separator starts: under the text, past the thumbnail. */
export const GALLERY_COLUMN_SEPARATOR_INSET = Space.md + COLUMN_THUMB_SIZE + Space.sm;

type Props = {
  item: AttachmentListItem;
  /** The prompt of a generated image, else the file name. */
  title: string;
  /** Shared or attached right now: a spinner, and taps wait. */
  busy?: boolean;
  onPress: () => void;
  /** `point` is where the finger was, so the item menu opens there. */
  onLongPress: (point: { x: number; y: number }) => void;
  onMissing: (attachmentId: string) => void;
  accessibilityHint?: string;
  accessibilityActions?: AccessibilityActionInfo[];
  onAccessibilityAction?: (event: AccessibilityActionEvent) => void;
};

/** One Library item in the column layout: thumbnail, name and its chat. */
export function GalleryColumnRow({
  item,
  title,
  busy = false,
  onPress,
  onLongPress,
  onMissing,
  accessibilityHint,
  accessibilityActions,
  onAccessibilityAction,
}: Props) {
  const C = useTheme();
  const s = useMemo(() => makeStyles(C), [C]);
  const isImage = isGalleryImage(item.content_type);
  const chatTitle = item.chat_title?.trim() || undefined;

  return (
    <ListRow
      appearance="plain"
      style={s.row}
      title={title}
      subtitle={chatTitle}
      numberOfLines={1}
      // A file name keeps its extension; a prompt reads best cut at the end.
      ellipsizeMode={item.source === "generated" ? "tail" : "middle"}
      busy={busy}
      leading={
        isImage ? (
          <GalleryThumbnail
            attachmentId={item.id}
            downloadUrl={item.download_url}
            size={COLUMN_THUMB_SIZE}
            onMissing={onMissing}
          />
        ) : (
          <View style={s.fileThumb}>
            <Icon name="file" size={IconSize.lg} color={C.textTertiary} />
          </View>
        )
      }
      onPress={onPress}
      onLongPress={(event) =>
        onLongPress({ x: event.nativeEvent.pageX, y: event.nativeEvent.pageY })
      }
      accessibilityLabel={chatTitle ? `${title}, ${chatTitle}` : title}
      accessibilityHint={accessibilityHint}
      accessibilityActions={accessibilityActions}
      onAccessibilityAction={onAccessibilityAction}
    />
  );
}

function makeStyles(C: Theme) {
  return StyleSheet.create({
    // Edge to edge, so the press highlight spans the screen.
    row: {
      borderRadius: 0,
      paddingHorizontal: Space.md,
      paddingVertical: Space.xs,
    },
    fileThumb: {
      width: COLUMN_THUMB_SIZE,
      height: COLUMN_THUMB_SIZE,
      borderRadius: Radius.sm,
      backgroundColor: C.surfaceAlt,
      borderWidth: 1,
      borderColor: C.border,
      alignItems: "center",
      justifyContent: "center",
    },
  });
}
