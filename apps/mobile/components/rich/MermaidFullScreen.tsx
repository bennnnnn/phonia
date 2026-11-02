/**
 * A Mermaid diagram on its own screen, drawn at its own size: a wide ER or
 * architecture diagram that the card shrinks to unreadable labels can be
 * panned here and pinched in or out. Same page file, sandbox and data as the
 * card (usePreviewPage); only the `natural` flag differs.
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { usePreviewPage } from "@/components/rich/usePreviewPage";
import { MERMAID_PAGE, mermaidPreviewConfig } from "@/lib/mermaidPreviewHtml";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { getPreviewWebView } from "@/lib/webView";
import { HeaderButton } from "@/ui/controls/HeaderButton";
import { FullScreenModal } from "@/ui/overlay/FullScreenModal";

type Props = {
  visible: boolean;
  /** The sanitized diagram source the card draws. */
  source: string;
  title: string;
  onClose: () => void;
};

/** The page's size reports only set a card's height; this screen fills the display. */
const ignoreMessage = () => undefined;

export function MermaidFullScreen({ visible, source, title, onClose }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const config = useMemo(
    () => mermaidPreviewConfig(source, theme, { natural: true }),
    [source, theme],
  );
  const previewWebView = getPreviewWebView();
  const WebView = previewWebView?.mode === "rnc" ? previewWebView.Component : null;
  const preview = usePreviewPage(MERMAID_PAGE, config, {
    active: visible && Boolean(WebView),
    onMessage: ignoreMessage,
  });

  return (
    <FullScreenModal
      visible={visible}
      presentationStyle="fullScreen"
      onRequestClose={onClose}
    >
      <View style={[s.root, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
        <View style={s.header}>
          <Text style={s.title} numberOfLines={1} accessibilityRole="header">
            {title}
          </Text>
          <HeaderButton
            icon="close"
            onPress={onClose}
            accessibilityLabel={t("preview.close")}
            testID="mermaid-full-screen-close"
          />
        </View>
        {visible && WebView && preview.status === "ready" ? (
          <WebView
            key={preview.webViewKey}
            {...preview.webViewProps}
            testID="mermaid-full-screen-diagram"
            style={s.webview}
            javaScriptEnabled
            domStorageEnabled={false}
            scrollEnabled
            bounces={false}
            overScrollMode="never"
            showsHorizontalScrollIndicator
            showsVerticalScrollIndicator
          />
        ) : (
          <View style={s.loading}>
            <ActivityIndicator color={theme.primary} />
          </View>
        )}
      </View>
    </FullScreenModal>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: t.bg },
    header: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
      paddingLeft: Space.md,
      paddingRight: Space.xs,
      paddingVertical: Space.xs,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: t.border,
    },
    title: { flex: 1, ...Type.label, ...Weight.bold, color: t.text },
    webview: { flex: 1, backgroundColor: "transparent" },
    loading: { flex: 1, alignItems: "center", justifyContent: "center" },
  });
}
