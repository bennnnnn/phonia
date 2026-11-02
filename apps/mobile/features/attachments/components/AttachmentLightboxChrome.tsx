import { useRef } from "react";
import { StyleSheet, View } from "react-native";
import type { EdgeInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/controls/Button";
import { HeaderButton } from "@/ui/controls/HeaderButton";
import { Menu } from "@/ui/overlay/Menu";
import { Space } from "@/lib/space";

type Props = {
  visible: boolean;
  overflowOpen: boolean;
  insets: EdgeInsets;
  busy: "download" | "share" | null;
  canShare: boolean;
  showUseInChat: boolean;
  showOpenChat: boolean;
  showDelete: boolean;
  onClose: () => void;
  onShare: () => void;
  onDownload: () => void;
  onToggleOverflow: () => void;
  onCloseOverflow: () => void;
  onUseInChat: () => void;
  onOpenChat: () => void;
  onDelete: () => void;
};

/**
 * The photo viewer's top bar: Close on the left; More (only when it has
 * items), Download and a white Share pill on the right. Nothing at the bottom.
 */
export function AttachmentLightboxChrome({
  visible,
  overflowOpen,
  insets,
  busy,
  canShare,
  showUseInChat,
  showOpenChat,
  showDelete,
  onClose,
  onShare,
  onDownload,
  onToggleOverflow,
  onCloseOverflow,
  onUseInChat,
  onOpenChat,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const moreRef = useRef<View>(null);
  const showOverflow = showUseInChat || showOpenChat || showDelete;
  if (!visible) return null;

  return (
    <>
      <View
        pointerEvents="box-none"
        style={[
          s.header,
          {
            paddingTop: Math.max(insets.top, Space.xs),
            paddingLeft: insets.left + Space.sm,
            paddingRight: insets.right + Space.sm,
          },
        ]}
      >
        <HeaderButton
          variant="media"
          icon="close"
          onPress={onClose}
          accessibilityLabel={t("preview.close")}
        />

        <View style={s.headerActions}>
          {showOverflow ? (
            <HeaderButton
              ref={moreRef}
              variant="media"
              icon="more-vertical"
              onPress={onToggleOverflow}
              accessibilityLabel={t("preview.more_a11y")}
            />
          ) : null}
          <HeaderButton
            variant="media"
            icon="download"
            onPress={onDownload}
            busy={busy === "download"}
            disabled={!canShare || busy != null}
            accessibilityLabel={t("common.download")}
          />
          <Button
            variant="media"
            title={t("preview.share")}
            onPress={onShare}
            loading={busy === "share"}
            disabled={!canShare || busy === "download"}
          />
        </View>
      </View>

      <Menu
        visible={overflowOpen && showOverflow}
        onClose={onCloseOverflow}
        anchorRef={moreRef}
        testID="lightbox-overflow-menu"
        items={[
          ...(showUseInChat
            ? [{ key: "use", icon: "attach" as const, label: t("gallery.use_in_chat"), onPress: onUseInChat }]
            : []),
          ...(showOpenChat
            ? [{ key: "open", icon: "message" as const, label: t("gallery.open_chat"), onPress: onOpenChat }]
            : []),
          ...(showDelete
            ? [{ key: "delete", icon: "trash" as const, label: t("common.delete"), destructive: true, onPress: onDelete }]
            : []),
        ]}
      />
    </>
  );
}

const s = StyleSheet.create({
  header: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 2,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingBottom: Space.xs,
  },
  headerActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: Space.xs,
  },
});
