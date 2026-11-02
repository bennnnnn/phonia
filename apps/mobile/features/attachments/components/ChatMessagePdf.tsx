import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";

import { AttachmentPdfViewer } from "@/features/attachments/components/AttachmentPdfViewer";
import { Icon } from "@/ui/icons/Icon";

import { useAuthToken } from "@/contexts/AuthContext";
import { useAttachmentIndexed } from "@/features/attachments/hooks/useAttachmentIndexed";
import { usePdfPreview } from "@/features/attachments/hooks/usePdfPreview";
import { useDeferredWebViewMount } from "@/hooks/useDeferredWebViewMount";
import { resolveAttachmentUri } from "@/features/attachments/model/attachmentUri";
import { downloadChatAttachment } from "@/features/attachments/model/downloadChatAttachment";
import { libraryActionMessage } from "@/features/attachments/model/attachmentErrors";
import { IconSize } from "@/ui/icons/sizes";
import { Theme, useTheme } from "@/lib/theme";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Type } from "@/lib/type";
import { getPreviewWebView } from "@/lib/webView";
import { alertDialog } from "@/ui/overlay/dialogs";

type Props = {
  attachmentId?: string | null;
  localUri?: string | null;
  path?: string | null;
  fileName?: string;
  compact?: boolean;
};

export function ChatMessagePdf({
  attachmentId,
  localUri,
  path,
  fileName = "document.pdf",
  compact = false,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme, compact), [theme, compact]);
  const token = useAuthToken();
  const { indexed, failed: indexFailed } = useAttachmentIndexed(attachmentId);
  const [viewerOpen, setViewerOpen] = useState(false);

  const remoteUri = useMemo(
    () => resolveAttachmentUri({ attachmentId, localUri, path }),
    [attachmentId, localUri, path],
  );

  const previewWebView = getPreviewWebView();
  const WebView = previewWebView?.Component;
  // The card's page-1 preview needs react-native-webview; Expo Go shows the card alone.
  const canRenderInline = previewWebView?.mode === "rnc";
  const { canMount, onLoaded } = useDeferredWebViewMount(
    Boolean(remoteUri && canRenderInline && !compact),
  );
  const preview = usePdfPreview({
    uri: remoteUri,
    fileName,
    enabled: Boolean(remoteUri && canRenderInline && !compact && canMount),
    allPages: false,
  });
  const previewFailed = preview.status === "failed";

  useEffect(() => {
    // Let the next deferred WebView mount instead of waiting on this card.
    if (previewFailed) onLoaded();
  }, [previewFailed, onLoaded]);

  const handleShare = useCallback(async () => {
    if (!remoteUri) return;
    try {
      await downloadChatAttachment({ uri: remoteUri, token, fileName });
    } catch (error) {
      void alertDialog({
        title: t("common.download_failed"),
        message: libraryActionMessage(error, "chat.pdf_export_failed", t),
      });
    }
  }, [remoteUri, token, fileName, t]);

  if (!remoteUri) return null;

  return (
    <>
      <Pressable
        style={s.card}
        onPress={() => setViewerOpen(true)}
        accessibilityLabel={t("chat.pdf_open_a11y", { fileName })}
        accessibilityRole="button"
      >
        <View style={s.iconWrap}>
          <Icon name="file-text" size={IconSize.md} color={theme.primary} />
        </View>
        <View style={s.meta}>
          <Text style={s.name} numberOfLines={2}>
            {fileName}
          </Text>
          <Text style={s.kind}>
            {indexFailed ? t("chat.file_index_failed") : indexed ? "PDF" : t("chat.file_indexing")}
          </Text>
        </View>
        <Icon name="chevron-right" size={IconSize.sm} color={theme.textTertiary} />
      </Pressable>

      {!compact && canRenderInline && WebView && canMount && preview.status === "ready" ? (
        <Pressable
          style={s.previewWrap}
          onPress={() => setViewerOpen(true)}
          // The card above opens the same viewer and is labelled; the page picture is for sight.
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
        >
          <WebView
            key={preview.webViewKey}
            {...preview.webViewProps}
            scrollEnabled={false}
            style={s.previewWeb}
            javaScriptEnabled
            onLoadEnd={onLoaded}
          />
        </Pressable>
      ) : !compact && canRenderInline && !previewFailed ? (
        <View style={[s.previewWrap, s.previewLoading]}>
          <ActivityIndicator color={theme.primary} />
        </View>
      ) : !compact && previewFailed ? (
        <Text style={s.fallbackHint}>{t("chat.pdf_preview_hint")}</Text>
      ) : null}

      <AttachmentPdfViewer
        visible={viewerOpen}
        onClose={() => setViewerOpen(false)}
        attachmentId={attachmentId}
        localUri={localUri}
        path={path}
        fileName={fileName}
        onShare={handleShare}
      />
    </>
  );
}

const CARD_WIDTH = 280;

function makeStyles(t: Theme, compact: boolean) {
  return StyleSheet.create({
    card: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
      paddingHorizontal: Space.sm,
      paddingVertical: compact ? 8 : 10,
      borderRadius: Radius.bubble,
      backgroundColor: t.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      // The preview below shares the card's width; sized by its content, the
      // column (aligned to the end) left the preview 0 wide and the page unseen.
      ...(compact ? { maxWidth: "100%" } : { width: CARD_WIDTH, maxWidth: "100%" }),
    },
    iconWrap: {
      width: 36,
      height: 36,
      borderRadius: Radius.sm,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: t.primaryLight,
    },
    meta: { flex: 1, minWidth: 0 },
    name: { ...Type.label, color: t.text },
    kind: { ...Type.meta, color: t.textTertiary, marginTop: 2 },
    previewWrap: {
      width: CARD_WIDTH,
      maxWidth: "100%",
      marginTop: Space.xs,
      height: 180,
      borderRadius: Radius.md,
      overflow: "hidden",
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      backgroundColor: t.bg,
    },
    // Only the spinner is centered: centered, react-native-webview's container
    // shrinks to its content and the page inside it lays out 0 wide.
    previewLoading: { alignItems: "center", justifyContent: "center" },
    previewWeb: { flex: 1, width: "100%", backgroundColor: "transparent" },
    fallbackHint: { ...Type.meta, color: t.textTertiary, marginTop: Space.xs },
  });
}
