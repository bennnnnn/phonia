import { useEffect, useMemo, type RefObject } from "react";
import { Keyboard, type View } from "react-native";
import { useTranslation } from "react-i18next";

import { Menu, type MenuEntry } from "@/ui/overlay/Menu";

type Props = {
  visible: boolean;
  title: string | null;
  pinned: boolean;
  /** The ⋮ button in the chat header. */
  anchorRef?: RefObject<View | null>;
  /** Or where a drawer row was long-pressed. */
  anchorPoint?: { x: number; y: number } | null;
  onClose: () => void;
  onShare: () => void;
  /** Chat ⋮ menu only — export the thread as PDF. */
  onExportPdf?: () => void;
  onRename: () => void;
  onTogglePin: () => void;
  onDelete: () => void;
  /** Drawer only — enter multi-select with this chat checked. */
  onSelectChats?: () => void;
};

/** Chat ⋮ and drawer long-press: one popover with the conversation's actions. */
export function ChatActionsMenu({
  visible,
  title,
  pinned,
  anchorRef,
  anchorPoint,
  onClose,
  onShare,
  onExportPdf,
  onRename,
  onTogglePin,
  onDelete,
  onSelectChats,
}: Props) {
  const { t } = useTranslation();

  useEffect(() => {
    if (visible) Keyboard.dismiss();
  }, [visible]);

  const items = useMemo(() => {
    const rows: MenuEntry[] = [
      { key: "share", icon: "share", label: t("chat.share"), onPress: onShare },
    ];
    if (onExportPdf) {
      rows.push({ key: "export-pdf", icon: "file-text", label: t("chat.export_pdf"), onPress: onExportPdf });
    }
    rows.push({ key: "rename", icon: "pencil", label: t("chat.rename"), onPress: onRename });
    rows.push({
      key: "pin",
      icon: pinned ? "pin-off" : "pin",
      label: pinned ? t("chat.unpin") : t("chat.pin"),
      onPress: onTogglePin,
    });
    if (onSelectChats) {
      rows.push({ key: "select", icon: "select", label: t("drawer.select"), onPress: onSelectChats });
    }
    rows.push({
      key: "delete",
      icon: "trash",
      label: t("common.delete"),
      onPress: onDelete,
      destructive: true,
    });
    return rows;
  }, [
    onDelete,
    onExportPdf,
    onRename,
    onSelectChats,
    onShare,
    onTogglePin,
    pinned,
    t,
  ]);

  return (
    <Menu
      visible={visible}
      onClose={onClose}
      items={items}
      title={title ?? undefined}
      anchorRef={anchorRef}
      anchorPoint={anchorPoint}
      testID="chat-actions-menu"
    />
  );
}
