import { useMemo } from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";

import {
  AttachmentViewerChrome,
  type AttachmentViewerProps,
} from "@/features/attachments/components/AttachmentViewerChrome";
import { usePdfPreview } from "@/features/attachments/hooks/usePdfPreview";
import { resolveAttachmentUri } from "@/features/attachments/model/attachmentUri";
import { Theme, useTheme } from "@/lib/theme";
import { Space } from "@/lib/space";
import { Type, Weight } from "@/lib/type";
import { getPreviewWebView } from "@/lib/webView";

type Props = AttachmentViewerProps & {
  attachmentId?: string | null;
  localUri?: string | null;
  path?: string | null;
};

/** Every page of the PDF, drawn as it scrolls into view. Closing stops the download. */
export function AttachmentPdfViewer({ visible, attachmentId, localUri, path, ...chrome }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeViewerStyles(theme), [theme]);

  const remoteUri = useMemo(
    () => resolveAttachmentUri({ attachmentId, localUri, path }),
    [attachmentId, localUri, path],
  );

  const WebView = getPreviewWebView()?.Component;
  const preview = usePdfPreview({
    uri: remoteUri,
    fileName: chrome.fileName,
    enabled: visible && Boolean(remoteUri),
    allPages: true,
  });

  return (
    <AttachmentViewerChrome
      {...chrome}
      visible={visible}
      closeLabel={t("chat.pdf_close_a11y")}
      shareLabel={t("chat.pdf_share_a11y")}
    >
      <View style={[s.body, (preview.status !== "ready" || !WebView) && s.centered]}>
        {preview.status === "loading" ? (
          <ActivityIndicator color={theme.primary} size="large" />
        ) : preview.status !== "ready" || !WebView ? (
          <Text style={s.error}>{t("chat.pdf_preview_failed")}</Text>
        ) : (
          <WebView
            key={preview.webViewKey}
            {...preview.webViewProps}
            style={s.webview}
            javaScriptEnabled
          />
        )}
      </View>
    </AttachmentViewerChrome>
  );
}

function makeViewerStyles(t: Theme) {
  return StyleSheet.create({
    body: { flex: 1 },
    // Only the spinner and the error are centered: centered, react-native-webview's
    // container shrinks to its content and the pages inside it lay out 0 wide.
    centered: { alignItems: "center", justifyContent: "center" },
    webview: { flex: 1, width: "100%", backgroundColor: t.bg },
    error: { ...Type.callout, ...Weight.regular, color: t.textSecondary, paddingHorizontal: Space.lg, textAlign: "center" },
  });
}
