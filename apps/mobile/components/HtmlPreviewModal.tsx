import {
  Component,
  useEffect,
  useMemo,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { CodeBlock } from "@/components/CodeBlock";
import type { IconName } from "@/ui/icons/names";
import { IconSize } from "@/ui/icons/sizes";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import {
  looksLikeInteractiveHtml,
  shareHtmlPreview,
  wrapFullDocument,
} from "@/lib/preview/openHtmlPreview";
import { HTML_RUN_EMPTY_KIND, prepareHtmlRunDocument } from "@/lib/preview/htmlRunDocument";
import { Space } from "@/lib/space";
import { Radius } from "@/lib/radius";
import {
  allowHtmlRunNavigation,
  getPreviewWebView,
  HTML_RUN_ORIGIN_WHITELIST,
} from "@/lib/webView";
import { FullScreenModal } from "@/ui/overlay/FullScreenModal";

// Expo Go has no react-native-webview: a static render (scripts stripped) stands in
// there. A build with the WebView never needs it, so a production bundle leaves the
// renderer and its CSS engine out (`__DEV__` folds to false; code-health audit DEAD-08).
const StaticHtmlPreview = __DEV__
  ? // eslint-disable-next-line @typescript-eslint/no-require-imports -- development only, so production bundles leave it out
    (require("@/components/StaticHtmlPreview") as typeof import("@/components/StaticHtmlPreview")).StaticHtmlPreview
  : null;

class PreviewRenderBoundary extends Component<
  {
    children: ReactNode;
    resetKey: string;
    errorColor: string;
    errorMessage: string;
  },
  { hasError: boolean }
> {
  state: { hasError: boolean } = { hasError: false };

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidUpdate(prevProps: { resetKey: string }): void {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn("HtmlPreviewModal render failed", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <View style={{ padding: Space.md }}>
          <Text
            style={{
              ...Type.secondary,
              color: this.props.errorColor,
              lineHeight: 20,
            }}
          >
            {this.props.errorMessage}
          </Text>
        </View>
      );
    }
    return this.props.children;
  }
}

type Props = {
  visible: boolean;
  html: string;
  onClose: () => void;
};

type PreviewTab = "run" | "code";

/**
 * Sandboxed HTML Run tab (RNC WebView only).
 *
 * Keep this path as close as charts: `source={{ html }}`, no baseUrl. The
 * model's page runs in a sandboxed frame inside that document, under the
 * wrapper's PREVIEW_CSP_LIVE (lib/preview/htmlRunDocument.ts), so it cannot navigate
 * the WebView, its own frame or open windows; CDN loads are allowed. The
 * WebView's navigations (on iOS, every frame's) also go through
 * allowHtmlRunNavigation, which keeps the tab's own documents and refuses the
 * rest without handing them to the OS (react-native-webview opens a URL
 * outside originWhitelist externally). No onOpenWindow and no
 * multiple windows: a window request is never handed to the app, and the
 * sandbox keeps the page from making one.
 */
function LiveWebPreview({
  html,
  theme,
  styles: s,
}: {
  html: string;
  theme: Theme;
  styles: ReturnType<typeof makeStyles>;
}) {
  const { t } = useTranslation();
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [empty, setEmpty] = useState(false);
  const previewWebView = useMemo(() => getPreviewWebView(), []);

  const fullHtml = useMemo(
    () => prepareHtmlRunDocument(wrapFullDocument(html, theme)),
    [html, theme],
  );
  const source = useMemo(() => ({ html: fullHtml }), [fullHtml]);

  useEffect(() => {
    setLoadError(null);
    setLoading(true);
    setEmpty(false);
  }, [html]);

  const WebView = previewWebView?.mode === "rnc" ? previewWebView.Component : null;
  if (!WebView) {
    return (
      <View style={s.scrollContent}>
        <Text style={s.base}>{t("preview.webview_unavailable")}</Text>
      </View>
    );
  }

  return (
    <View style={s.webviewContainer} collapsable={false}>
      {loadError ? (
        <View style={s.emptyOverlay} pointerEvents="none">
          <Text style={s.emptyOverlayText}>{loadError}</Text>
        </View>
      ) : empty ? (
        <View style={s.emptyOverlay} pointerEvents="none">
          <Text style={s.emptyOverlayText}>{t("preview.empty_sandbox")}</Text>
        </View>
      ) : loading ? (
        <View style={s.emptyOverlay} pointerEvents="none">
          <ActivityIndicator color={theme.primary} />
          <Text style={[s.emptyOverlayText, { marginTop: Space.xs }]}>
            {t("preview.loading")}
          </Text>
        </View>
      ) : null}
      <WebView
        source={source}
        style={s.webview}
        scrollEnabled
        originWhitelist={HTML_RUN_ORIGIN_WHITELIST}
        onShouldStartLoadWithRequest={allowHtmlRunNavigation}
        javaScriptEnabled
        domStorageEnabled={false}
        allowsInlineMediaPlayback
        setSupportMultipleWindows={false}
        nestedScrollEnabled
        onLoadStart={() => setLoading(true)}
        onLoadEnd={() => setLoading(false)}
        onMessage={(e: { nativeEvent?: { data?: string } }) => {
          try {
            const data = JSON.parse(e.nativeEvent?.data ?? "{}");
            if (data && data.kind === HTML_RUN_EMPTY_KIND) setEmpty(true);
          } catch {
            /* ignore non-JSON messages */
          }
        }}
        onError={(e: { nativeEvent?: { description?: string } }) => {
          const detail = e.nativeEvent?.description?.trim();
          setLoadError(detail || t("preview.load_error"));
        }}
      />
    </View>
  );
}

function ToolbarItem({
  icon,
  label,
  onPress,
  active,
  theme,
  styles: s,
}: {
  icon: IconName;
  label: string;
  onPress: () => void;
  active?: boolean;
  theme: Theme;
  styles: ReturnType<typeof makeStyles>;
}) {
  const color = active ? theme.primary : theme.textSecondary;
  return (
    <Pressable
      style={[s.toolbarItem, active && s.toolbarItemActive]}
      onPress={onPress}
      hitSlop={8}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ selected: active }}
    >
      <Icon name={icon} size={IconSize.md} color={color} />
    </Pressable>
  );
}

export function HtmlPreviewModal({ visible, html, onClose }: Props) {
  const insets = useSafeAreaInsets();
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const { width } = useWindowDimensions();
  const contentWidth = Math.max(width - 32, 280);
  const [tab, setTab] = useState<PreviewTab>("run");
  const interactive = useMemo(() => looksLikeInteractiveHtml(html), [html]);
  // Bare RNC only — do not treat expo-dom as a live Run path (file:// blanks).
  const canUseNativeWebView = useMemo(
    () => getPreviewWebView()?.mode === "rnc",
    [],
  );

  useEffect(() => {
    if (visible) setTab("run");
  }, [visible]);

  return (
    <FullScreenModal
      visible={visible}
      animationType="slide"
      presentationStyle="fullScreen"
      onRequestClose={onClose}
    >
      <View
        style={[s.root, { paddingTop: insets.top, paddingBottom: insets.bottom }]}
      >
        {tab === "run" && interactive && !canUseNativeWebView ? (
          <View style={s.interactiveBanner}>
            <Icon name="zap" size={IconSize.xs} color={theme.primary} />
            <Text style={s.interactiveBannerText}>{t("preview.expo_go_banner")}</Text>
          </View>
        ) : null}

        <View style={s.body}>
          {tab === "code" ? (
            <ScrollView
              style={s.codeScroll}
              contentContainerStyle={s.codeScrollContent}
              showsVerticalScrollIndicator
            >
              <CodeBlock code={html} lang="html" />
            </ScrollView>
          ) : canUseNativeWebView ? (
            <PreviewRenderBoundary
              resetKey={html}
              errorColor={theme.danger}
              errorMessage={t("preview.render_failed")}
            >
              <LiveWebPreview html={html} theme={theme} styles={s} />
            </PreviewRenderBoundary>
          ) : StaticHtmlPreview ? (
            <StaticHtmlPreview html={html} contentWidth={contentWidth} theme={theme} styles={s} />
          ) : (
            <LiveWebPreview html={html} theme={theme} styles={s} />
          )}
        </View>

        <View style={s.toolbar}>
          <ToolbarItem
            icon="close"
            label={t("preview.close")}
            onPress={onClose}
            theme={theme}
            styles={s}
          />
          <ToolbarItem
            icon="code"
            label={t("preview.code_tab")}
            onPress={() => setTab("code")}
            active={tab === "code"}
            theme={theme}
            styles={s}
          />
          <ToolbarItem
            icon="play"
            label={t("preview.run_tab")}
            onPress={() => setTab("run")}
            active={tab === "run"}
            theme={theme}
            styles={s}
          />
          <ToolbarItem
            icon="share"
            label={t("preview.share")}
            onPress={() => void shareHtmlPreview(html)}
            theme={theme}
            styles={s}
          />
        </View>
      </View>
    </FullScreenModal>
  );
}

const makeStyles = (theme: Theme) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: theme.bg },
    interactiveBanner: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      marginHorizontal: Space.md,
      marginTop: Space.sm,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.sm,
      borderRadius: Radius.sm,
      backgroundColor: theme.primaryLight,
    },
    interactiveBannerText: {
      flex: 1,
      ...Type.compact,
      color: theme.text,
    },
    body: { flex: 1, minHeight: 0 },
    codeScroll: { flex: 1 },
    codeScrollContent: { padding: Space.md, paddingBottom: Space.lg },
    webviewContainer: {
      flex: 1,
      alignSelf: "stretch",
      position: "relative",
      minHeight: 200,
      backgroundColor: theme.bg,
    },
    // Absolute fill — never gate mount on onLayout height (Modal blank bug).
    webview: {
      position: "absolute",
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
      backgroundColor: theme.bg,
    },
    emptyOverlay: {
      position: "absolute",
      zIndex: 2,
      top: Space.md,
      left: Space.md,
      right: Space.md,
      padding: Space.md,
      borderRadius: Radius.sm,
      backgroundColor: theme.surfaceAlt,
    },
    emptyOverlayText: {
      ...Type.secondary,
      lineHeight: 20,
      color: theme.text,
    },
    scroll: { flex: 1 },
    scrollContent: { paddingHorizontal: Space.md, paddingVertical: Space.md, paddingBottom: Space.md },
    // No fixed lineHeight: 22 on 16pt clipped tall scripts (Amharic, Thai).
    base: { ...Type.body, color: theme.text },
    toolbar: {
      flexDirection: "row",
      alignItems: "stretch",
      justifyContent: "space-around",
      paddingHorizontal: Space.xs,
      paddingTop: Space.xs,
      paddingBottom: Space.xs,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: theme.border,
      backgroundColor: theme.bg,
    },
    toolbarItem: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      paddingVertical: Space.xs,
      borderRadius: Radius.sm,
    },
    toolbarItemActive: {
      backgroundColor: theme.primaryLight,
    },
  });
