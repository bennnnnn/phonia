import { useTranslation } from "react-i18next";

import { Menu, type MenuEntry } from "@/ui/overlay/Menu";
import { galleryItemActions, type GalleryItemAction } from "@/features/attachments/model/gallery";

type Props = {
  visible: boolean;
  canOpenChat: boolean;
  /** Where the tile was long-pressed. */
  anchorPoint: { x: number; y: number } | null;
  onClose: () => void;
  onUseInChat: () => void;
  onOpenChat: () => void;
  onShare: () => void;
  onDelete: () => void;
};

/** Library long-press: use, open, share, or delete one photo or file. */
export function GalleryItemActionsMenu({
  visible,
  canOpenChat,
  anchorPoint,
  onClose,
  onUseInChat,
  onOpenChat,
  onShare,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const entries: Record<GalleryItemAction, MenuEntry> = {
    use: { key: "use", icon: "attach", label: t("gallery.use_in_chat"), onPress: onUseInChat },
    open_chat: { key: "open", icon: "message", label: t("gallery.open_chat"), onPress: onOpenChat },
    share: { key: "share", icon: "share", label: t("gallery.share"), onPress: onShare },
    delete: { key: "delete", icon: "trash", label: t("common.delete"), onPress: onDelete, destructive: true },
  };
  const items = galleryItemActions({ chat_id: canOpenChat ? "chat" : null }).map((action) => entries[action]);

  return (
    <Menu
      visible={visible}
      onClose={onClose}
      anchorPoint={anchorPoint}
      items={items}
      testID="gallery-item-menu"
    />
  );
}
