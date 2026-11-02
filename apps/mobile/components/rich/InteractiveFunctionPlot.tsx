import { Suspense, useMemo, type RefObject } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { ExplorerModal } from "@/components/rich/ExplorerModal";
import { GraphCanvas, GRAPH_AXIS_PAD } from "@/components/rich/GraphCanvas";
import { SkiaGraphCanvasLazy } from "@/components/rich/skia/SkiaGraphCanvasLazy";
import { CHART_HEIGHT, GRAPH_CARD_INSET, useFunctionPlotState } from "@/components/rich/useFunctionPlotState";
import { type DrawnSeries } from "@/hooks/useInteractiveGraph";
import { CODE_FACE } from "@/lib/fonts";
import { formatGraphExpr } from "@/lib/math/graphBlock";
import { xAxisInPi } from "@/lib/math/graphFit";
import { type GraphSpec } from "@/lib/math/graphSpec";
import { IconSize } from "@/ui/icons/sizes";
import { Space } from "@/lib/space";
import { Type } from "@/lib/type";
import { Theme } from "@/lib/theme";
import { Radius } from "@/lib/radius";
import { useLiveAnnouncement } from "@/ui/hooks/useLiveAnnouncement";

const MODAL_LIST_MAX = 220;

type Props = {
  spec: GraphSpec;
  chartWidth: number;
  styles: {
    wrap: object;
    title: object;
  };
  theme: Theme;
};

export function InteractiveFunctionPlot({ spec, chartWidth, styles, theme }: Props) {
  const { t } = useTranslation();
  const plot = useFunctionPlotState(spec, chartWidth, theme);
  const { card, explorer, editor, holes, verticalX } = plot;
  const explorerStyles = useMemo(() => makeExplorerStyles(theme), [theme]);
  const customTitle =
    spec.title != null && spec.title.trim() !== "" && spec.title.trim() !== spec.expr
      ? formatGraphExpr(spec.title)
      : null;
  const seriesEditor = (rows: DrawnSeries[], mode: "card" | "modal") =>
    spec.type === "function" ? (
      <SeriesList
        rows={rows}
        theme={theme}
        styles={explorerStyles}
        canAdd={editor.canAdd}
        scrollRef={mode === "modal" ? editor.seriesListRef : undefined}
        onChangeExpr={editor.setExpr}
        onToggle={editor.toggleVisible}
        onRemove={editor.removeSeries}
        onAdd={mode === "modal" ? editor.addSeriesAndReveal : editor.addSeries}
      />
    ) : null;
  const svgCard = (
    <GraphCanvas
      spec={spec}
      theme={theme}
      clipId={card.clipId}
      width={card.width}
      height={CHART_HEIGHT}
      bounds={card.bounds}
      drawn={card.drawn}
      holes={holes}
      verticalX={verticalX}
    />
  );

  return (
    <View
      style={[styles.wrap, explorerStyles.card]}
      onLayout={card.onLayout}
      testID="graph-card"
    >
      {customTitle ? <Text style={styles.title}>{customTitle}</Text> : null}
      {verticalX != null ? (
        <Text style={styles.title}>{formatGraphExpr(spec.title ?? spec.expr)}</Text>
      ) : null}
      <Pressable
        onPress={plot.openExplorer}
        testID="graph-expand"
        accessibilityRole="button"
        accessibilityLabel={t("rich.expand")}
        style={[explorerStyles.plotPress, { width: card.width, height: CHART_HEIGHT }]}
      >
        {plot.skia ? (
          <Suspense fallback={svgCard}>
            <SkiaGraphCanvasLazy
              drawn={card.drawn}
              holes={holes}
              verticalX={verticalX}
              xName={spec.variable ?? "x"}
              yName="y"
              xInPi={xAxisInPi(spec)}
              width={card.width}
              height={CHART_HEIGHT}
              pad={GRAPH_AXIS_PAD}
              theme={theme}
              viewport={card.skiaViewport}
              testID="skia-graph-card"
            />
          </Suspense>
        ) : (
          svgCard
        )}
        <View
          style={explorerStyles.expandBadge}
          pointerEvents="none"
          testID="graph-expand-cue"
        >
          <Icon name="expand" size={IconSize.xs} color={theme.textSecondary} />
        </View>
      </Pressable>
      {plot.open ? null : seriesEditor(card.drawn, "card")}
      <ExplorerModal
        open={plot.open}
        onClose={plot.closeExplorer}
        theme={theme}
        insets={plot.insets}
        spec={spec}
        clipId={explorer.clipId}
        plot={explorer.plot}
        onPlotLayout={explorer.onPlotLayout}
        bounds={explorer.viewport.bounds}
        gesture={explorer.viewport.gesture}
        drawn={explorer.drawn}
        holes={holes}
        verticalX={verticalX}
        editor={seriesEditor(explorer.drawn, "modal")}
        skia={plot.skia}
        initialView={explorer.initialView}
        onCommitBounds={explorer.viewport.commitBounds}
      />
    </View>
  );
}

function SeriesList({
  rows,
  theme,
  styles,
  canAdd,
  scrollRef,
  onChangeExpr,
  onToggle,
  onRemove,
  onAdd,
}: {
  rows: DrawnSeries[];
  theme: Theme;
  styles: ReturnType<typeof makeExplorerStyles>;
  canAdd: boolean;
  scrollRef?: RefObject<ScrollView | null>;
  onChangeExpr: (id: string, text: string) => void;
  onToggle: (id: string) => void;
  onRemove: (id: string) => void;
  onAdd: () => void;
}) {
  const { t } = useTranslation();
  const body = (
    <>
      {rows.map((row) => (
        <SeriesRow
          key={row.id}
          row={row}
          theme={theme}
          styles={styles}
          onChangeExpr={(text) => onChangeExpr(row.id, text)}
          onToggle={() => onToggle(row.id)}
          onRemove={() => onRemove(row.id)}
        />
      ))}
      {canAdd ? (
        <Pressable
          onPress={onAdd}
          testID="graph-add-function"
          accessibilityRole="button"
          accessibilityLabel={t("rich.graph_add_function")}
          hitSlop={{ top: 9, bottom: 9 }}
          style={styles.addBtn}
        >
          <Icon name="plus" size={IconSize.xs} color={theme.primary} />
          <Text style={styles.addText}>{t("rich.graph_add_function")}</Text>
        </Pressable>
      ) : null}
    </>
  );
  if (scrollRef) {
    return (
      <ScrollView
        ref={scrollRef}
        testID="graph-series-scroll"
        style={styles.modalList}
        contentContainerStyle={styles.modalListContent}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
      >
        {body}
      </ScrollView>
    );
  }
  return <View style={styles.list}>{body}</View>;
}

function SeriesRow({
  row,
  theme,
  styles,
  onChangeExpr,
  onToggle,
  onRemove,
}: {
  row: DrawnSeries;
  theme: Theme;
  styles: ReturnType<typeof makeExplorerStyles>;
  onChangeExpr: (text: string) => void;
  onToggle: () => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const inputId = row.locked ? "graph-expr-input" : `graph-expr-input-${row.id}`;
  useLiveAnnouncement(row.invalid ? t("rich.graph_invalid") : null);
  return (
    <View style={styles.row}>
      <View style={[styles.swatch, { backgroundColor: row.color, opacity: row.visible ? 1 : 0.35 }]} />
      <View style={styles.expr}>
        <TextInput
          value={row.expr}
          onChangeText={onChangeExpr}
          autoCapitalize="none"
          autoCorrect={false}
          spellCheck={false}
          accessibilityLabel={t("rich.graph_expr_a11y")}
          testID={inputId}
          placeholder={t("rich.graph_expr_placeholder")}
          placeholderTextColor={theme.textSecondary}
          style={[
            styles.input,
            row.invalid && styles.inputInvalid,
            !row.visible && styles.dim,
          ]}
        />
        {row.invalid ? (
          <Text style={styles.invalidNote} accessibilityLiveRegion="polite">
            {t("rich.graph_invalid")}
          </Text>
        ) : null}
      </View>
      {row.locked ? null : (
        <>
          <Pressable
            onPress={onToggle}
            testID={`graph-hide-${row.id}`}
            accessibilityRole="button"
            accessibilityLabel={row.visible ? t("rich.graph_hide_series") : t("rich.graph_show_series")}
            hitSlop={8}
            style={styles.iconBtn}
          >
            <Icon
              name={row.visible ? "eye" : "eye-off"}
              size={IconSize.sm}
              color={theme.textSecondary}
            />
          </Pressable>
          <Pressable
            onPress={onRemove}
            testID={`graph-remove-${row.id}`}
            accessibilityRole="button"
            accessibilityLabel={t("rich.graph_remove_series")}
            hitSlop={8}
            style={styles.iconBtn}
          >
            <Icon name="trash" size={IconSize.sm} color={theme.textSecondary} />
          </Pressable>
        </>
      )}
    </View>
  );
}

const makeExplorerStyles = (theme: Theme) =>
  StyleSheet.create({
    card: {
      alignSelf: "stretch",
      alignItems: "stretch",
      width: "100%",
      padding: GRAPH_CARD_INSET,
    },
    plotPress: {
      position: "relative",
      alignSelf: "stretch",
      borderWidth: 1,
      borderColor: theme.isDark ? theme.border : theme.primaryLight,
      borderRadius: Radius.md,
      backgroundColor: theme.surface,
      overflow: "hidden",
    },
    expandBadge: {
      position: "absolute",
      bottom: 8,
      right: 8,
      width: 28,
      height: 28,
      alignItems: "center",
      justifyContent: "center",
    },
    modalList: {
      flexGrow: 0,
      flexShrink: 1,
      maxHeight: MODAL_LIST_MAX,
    },
    modalListContent: {
      paddingHorizontal: Space.md,
      paddingTop: Space.xs,
      paddingBottom: Space.sm,
      gap: Space.xs,
    },
    list: {
      alignSelf: "stretch",
      marginTop: Space.xs,
      gap: Space.xs,
    },
    row: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
    },
    swatch: {
      width: 8,
      height: 8,
      borderRadius: Radius.full,
    },
    expr: {
      flex: 1,
    },
    input: {
      margin: 0,
      paddingVertical: 2,
      ...CODE_FACE,
      fontSize: 15,
      color: theme.text,
    },
    inputInvalid: {
      color: theme.danger,
    },
    invalidNote: {
      ...Type.caption,
      color: theme.danger,
    },
    dim: {
      opacity: 0.4,
    },
    iconBtn: {
      padding: Space.xxs,
    },
    addBtn: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xxs,
      alignSelf: "flex-start",
      paddingVertical: Space.xxs,
    },
    addText: {
      ...Type.label,
      color: theme.primary,
    },
  });
