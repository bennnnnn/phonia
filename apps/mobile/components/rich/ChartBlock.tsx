/**
 * Chart block — renders ```chart / ```vega / ```vega-lite / ```plot fences
 * inline via WebView + Vega-Embed so the user sees the actual chart, not raw JSON.
 * A body it cannot draw (lib/chartSpec.ts), or one the page drew nothing for, shows
 * ChartFallback: a note and the chart's data as a table. The card has no source, copy
 * or editor buttons: its only control is expand, on a chart taller than the card.
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { Icon } from "@/ui/icons/Icon";

import { ChartFallback } from "@/components/rich/ChartFallback";
import { useFenceRefused } from "@/components/rich/useFenceRefused";
import { usePreviewPage } from "@/components/rich/usePreviewPage";
import { useWebPreviewHeight } from "@/components/rich/useWebPreviewHeight";
import { VisualCard } from "@/components/rich/VisualCard";
import { useDeferredWebViewMount } from "@/hooks/useDeferredWebViewMount";
import { CHART_PAGE, chartPreviewConfig } from "@/lib/chartPreviewHtml";
import { CHART_HEIGHT_EPSILON_PX, CHART_PREVIEW_HEIGHT } from "@/lib/chartPreviewHeight";
import { readChart } from "@/lib/chartSpec";
import { IconSize } from "@/ui/icons/sizes";
import { Theme, useTheme } from "@/lib/theme";
import { Space } from "@/lib/space";
import { Type } from "@/lib/type";
import { getPreviewWebView } from "@/lib/webView";

type Props = { content: string };

const CHART_BODY = { json: true };

export function ChartBlock({ content }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [viewWidth, setViewWidth] = useState(0);
  const { expanded, height, clipped, renderError, onMessage, toggleExpanded } =
    useWebPreviewHeight({
      rules: CHART_PREVIEW_HEIGHT,
      page: "chart",
      errorText: t("rich.chart_error"),
    });

  const read = useMemo(() => readChart(content), [content]);
  const plotWidth = viewWidth > 0 ? viewWidth - 16 : 320;
  const config = useMemo(
    () => chartPreviewConfig(content, theme, plotWidth),
    [content, theme, plotWidth],
  );
  const previewWebView = getPreviewWebView();
  const WebView = previewWebView?.Component;
  const canRenderInlineChart = previewWebView?.mode === "rnc";
  const drawable = read.spec !== null;
  const preview = usePreviewPage(CHART_PAGE, config, {
    active: Boolean(WebView) && canRenderInlineChart && drawable,
    onMessage,
  });
  const { canMount, onLoaded } = useDeferredWebViewMount(
    Boolean(WebView) && canRenderInlineChart && drawable && preview.status === "ready",
  );
  const previewError = preview.status === "failed" ? t("rich.chart_error") : null;
  const undrawn = !drawable || renderError !== null;
  useFenceRefused("chart", content, !drawable, CHART_BODY);

  return (
    <VisualCard
      label={t("rich.chart")}
      icon="bar-chart"
      onLayout={(e) => {
        const w = Math.floor(e.nativeEvent.layout.width);
        if (w > 0 && Math.abs(w - viewWidth) > CHART_HEIGHT_EPSILON_PX) setViewWidth(w);
      }}
      actions={
        clipped || expanded ? (
          <Pressable
            style={s.iconBtn}
            onPress={toggleExpanded}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel={expanded ? t("rich.collapse") : t("rich.expand")}
          >
            <Icon
              name={expanded ? "collapse" : "expand"}
              size={IconSize.sm}
              color={theme.textSecondary}
            />
          </Pressable>
        ) : null
      }
    >
      <View style={[s.previewBox, undrawn ? null : { height }]}>
        {undrawn ? (
          <ChartFallback table={read.table} />
        ) : previewError ? (
          <View style={[s.previewPlaceholder, { height }]}>
            <Icon name="alert-circle" size={IconSize.sm} color={theme.danger} />
            <Text style={[s.previewPlaceholderText, { color: theme.danger }]}>
              {previewError}
            </Text>
          </View>
        ) : WebView && canRenderInlineChart ? (
          canMount && preview.status === "ready" ? (
            <WebView
              key={preview.webViewKey}
              {...preview.webViewProps}
              style={[s.webview, { height, width: viewWidth > 0 ? viewWidth : 320 }]}
              scrollEnabled={clipped}
              nestedScrollEnabled={clipped}
              showsVerticalScrollIndicator={clipped}
              javaScriptEnabled
              domStorageEnabled={false}
              onLoadEnd={onLoaded}
            />
          ) : (
            <View style={[s.previewPlaceholder, { height }]}>
              <ActivityIndicator color={theme.primary} />
            </View>
          )
        ) : (
          <View style={[s.previewPlaceholder, { height }]}>
            <Text style={s.previewPlaceholderText}>
              {t("rich.chart_dev_build")}
            </Text>
          </View>
        )}
      </View>
    </VisualCard>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    // The page paints its background once its chart arrives; until then the card's shows.
    webview: { backgroundColor: "transparent" },
    previewBox: { backgroundColor: t.bg, overflow: "hidden" },
    previewPlaceholder: {
      alignItems: "center",
      justifyContent: "center",
      paddingHorizontal: Space.md,
    },
    previewPlaceholderText: {
      ...Type.compact,
      color: t.textSecondary,
      textAlign: "center",
    },
    iconBtn: {
      width: 32,
      height: 32,
      alignItems: "center",
      justifyContent: "center",
    },
  });
}
