/**
 * Mermaid diagram — inline SVG render via WebView (dev build), with source fallback.
 */
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import * as Clipboard from "expo-clipboard";
import * as WebBrowser from "expo-web-browser";
import { Icon } from "@/ui/icons/Icon";

import { CopyButton } from "@/components/CopyButton";
import { MermaidFullScreen } from "@/components/rich/MermaidFullScreen";
import { usePreviewPage } from "@/components/rich/usePreviewPage";
import { useWebPreviewHeight } from "@/components/rich/useWebPreviewHeight";
import { VisualCard } from "@/components/rich/VisualCard";
import { useDeferredWebViewMount } from "@/hooks/useDeferredWebViewMount";
import { CODE_FACE } from "@/lib/fonts";
import { mermaidTitleKey } from "@/lib/mermaidKind";
import { MERMAID_MIN_HEIGHT, MERMAID_PREVIEW_HEIGHT } from "@/lib/mermaidPreviewHeight";
import { MERMAID_PAGE, mermaidPreviewConfig } from "@/lib/mermaidPreviewHtml";
import { sanitizeMermaidNodeLabels } from "@/lib/mermaidSanitize";
import { Theme, useTheme } from "@/lib/theme";
import { getPreviewWebView } from "@/lib/webView";
import { IconSize } from "@/ui/icons/sizes";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Type, Weight } from "@/lib/type";

type Props = { content: string };

export function MermaidBlock({ content }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [showSource, setShowSource] = useState(false);
  const [fullScreen, setFullScreen] = useState(false);
  const { expanded, height, clipped, renderError, onMessage, toggleExpanded } =
    useWebPreviewHeight({
      rules: MERMAID_PREVIEW_HEIGHT,
      page: "mermaid",
      errorText: t("rich.mermaid_error"),
    });

  const sanitized = useMemo(() => sanitizeMermaidNodeLabels(content.trim()), [content]);
  const config = useMemo(() => mermaidPreviewConfig(sanitized, theme), [sanitized, theme]);
  const previewWebView = getPreviewWebView();
  const WebView = previewWebView?.Component;
  const canRenderInline = previewWebView?.mode === "rnc";
  const preview = usePreviewPage(MERMAID_PAGE, config, {
    active: Boolean(WebView) && canRenderInline,
    onMessage,
  });
  const { canMount, onLoaded } = useDeferredWebViewMount(
    Boolean(WebView) && canRenderInline && preview.status === "ready",
  );
  const previewError = preview.status === "failed" ? t("rich.mermaid_error") : null;
  const title = t(mermaidTitleKey(sanitized));

  return (
    <VisualCard
      label={title}
      icon="network"
      headerRight={
        <Pressable
          onPress={() => setShowSource((v) => !v)}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel={showSource ? t("rich.diagram") : t("rich.source")}
        >
          <Icon
            name={showSource ? "eye-off" : "code"}
            size={IconSize.sm}
            color={theme.primary}
          />
        </Pressable>
      }
      actions={
        <MermaidActions
          source={sanitized}
          sizeToggle={clipped || expanded ? { expanded, toggle: toggleExpanded } : null}
          onFullScreen={canRenderInline && WebView ? () => setFullScreen(true) : null}
          theme={theme}
          styles={s}
        />
      }
    >
      <MermaidFullScreen
        visible={fullScreen}
        source={sanitized}
        title={title}
        onClose={() => setFullScreen(false)}
      />
      {renderError || previewError ? (
        <View style={s.previewBox}>
          <Icon name="alert-circle" size={IconSize.sm} color={theme.danger} />
          <Text style={[s.previewText, { color: theme.danger }]}>
            {renderError ?? previewError}
          </Text>
        </View>
      ) : showSource ? (
        <View style={s.previewBox}>
          <Text style={s.previewText}>{sanitized}</Text>
        </View>
      ) : canRenderInline && WebView ? (
        canMount && preview.status === "ready" ? (
          <View style={[s.webWrap, { height }]}>
            <WebView
              key={preview.webViewKey}
              {...preview.webViewProps}
              scrollEnabled={clipped}
              nestedScrollEnabled={clipped}
              showsVerticalScrollIndicator={clipped}
              bounces={false}
              overScrollMode="never"
              style={s.webview}
              javaScriptEnabled
              domStorageEnabled={false}
              onLoadEnd={onLoaded}
            />
          </View>
        ) : (
          <View style={s.loadingWrap}>
            <ActivityIndicator color={theme.primary} />
          </View>
        )
      ) : (
        <View style={s.previewBox}>
          <Text style={s.previewText} numberOfLines={6}>
            {sanitized}
          </Text>
          <Text style={s.fallbackHint}>{t("rich.mermaid_dev_build")}</Text>
        </View>
      )}
    </VisualCard>
  );
}

/** Copy, the card's height toggle, full screen, and the online editor. */
function MermaidActions({
  source,
  sizeToggle,
  onFullScreen,
  theme,
  styles: s,
}: {
  source: string;
  sizeToggle: { expanded: boolean; toggle: () => void } | null;
  onFullScreen: (() => void) | null;
  theme: Theme;
  styles: ReturnType<typeof makeStyles>;
}) {
  const { t } = useTranslation();
  // The source goes to the clipboard only; mermaid.live opens empty and the
  // user pastes it there.
  const openEditor = useCallback(async () => {
    await Clipboard.setStringAsync(source);
    await WebBrowser.openBrowserAsync("https://mermaid.live/edit");
  }, [source]);

  return (
    <>
      <CopyButton text={source} />
      {sizeToggle ? (
        <Pressable
          style={s.iconBtn}
          onPress={sizeToggle.toggle}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel={sizeToggle.expanded ? t("rich.collapse") : t("rich.expand")}
        >
          <Icon
            name={sizeToggle.expanded ? "collapse" : "expand"}
            size={IconSize.sm}
            color={theme.textSecondary}
          />
        </Pressable>
      ) : null}
      {onFullScreen ? (
        <Pressable
          style={s.iconBtn}
          onPress={onFullScreen}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel={t("rich.diagram_full_screen")}
        >
          <Icon name="scan" size={IconSize.sm} color={theme.textSecondary} />
        </Pressable>
      ) : null}
      <Pressable
        style={s.openBtn}
        onPress={openEditor}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel={t("rich.mermaid_editor")}
        accessibilityHint={t("rich.mermaid_editor_hint")}
      >
        <Icon name="external-link" size={IconSize.sm} color={theme.onPrimary} />
        <Text style={s.openLabel} numberOfLines={1}>
          {t("rich.mermaid_editor")}
        </Text>
      </Pressable>
    </>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    webWrap: { backgroundColor: t.bg },
    webview: { flex: 1, backgroundColor: "transparent" },
    loadingWrap: {
      height: MERMAID_MIN_HEIGHT,
      backgroundColor: t.bg,
      alignItems: "center",
      justifyContent: "center",
    },
    previewBox: {
      paddingHorizontal: Space.sm,
      paddingVertical: Space.sm,
      backgroundColor: t.contentSurface,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: t.border,
    },
    previewText: { ...Type.meta, ...CODE_FACE, lineHeight: 18, color: t.textSecondary },
    fallbackHint: { ...Type.meta, color: t.textTertiary, marginTop: Space.xs },
    iconBtn: {
      width: 32,
      height: 32,
      alignItems: "center",
      justifyContent: "center",
    },
    openBtn: {
      flexShrink: 1,
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      paddingVertical: Space.sm,
      paddingHorizontal: Space.md,
      borderRadius: Radius.sm,
      backgroundColor: t.primary,
    },
    openLabel: { ...Type.label, ...Weight.bold, color: t.onPrimary, flexShrink: 1 },
  });
}
