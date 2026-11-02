/**
 * Minimal markdown when the rich renderer fails — still formats headers,
 * tables, bold, and code (no Prism / rich cards). Callout fences render as
 * styled prose instead of raw "callout-tip" code. Geometry/graph fences keep
 * their SVG renderers so densified point dumps never become a wall of JSON;
 * those load on first use, as in the rich renderer, so the chat screen never
 * loads them (or Skia) at launch through this fallback.
 * Sources, places, answers, and heavy visuals degrade to a short summary.
 */
import { useMemo } from "react";
import Markdown, {
  renderRules as defaultRules,
  type RenderRules,
} from "react-native-markdown-display";
import { StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { inlineCodeTextStyle } from "@/components/markdown/markdownContentStyles";
import { LazyFunctionGraphBlock, LazyGeometryBlock } from "@/components/rich/LazyHeavyRich";
import { codeLanguageLabel } from "@/lib/codeHighlight";
import { CODE_FACE } from "@/lib/fonts";
import { markdownItInstance } from "@/lib/markdown/parser";
import { preprocessMarkdown } from "@/lib/markdown/preprocess";
import { classifyFallbackFence } from "@/lib/fallbackFence";
import { documentFormForLang, fenceIdForLang } from "@/lib/fenceRegistry";
import { mermaidTitleKey } from "@/lib/mermaidKind";
import { Theme, useTheme } from "@/lib/theme";
import { Italic, Type, Weight } from "@/lib/type";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";

// react-native-markdown-display's AST exposes the fence's language tag as
// `sourceInfo`, not `info` — see markdownFenceRender.tsx's FenceNode.
type FenceNode = { key: string; content: string; sourceInfo?: string };

type Props = { content: string };

const CALLOUT_I18N_KEYS: Record<string, string> = {
  tip: "rich.callout_tip",
  note: "rich.callout_note",
  warning: "rich.callout_warning",
  info: "rich.callout_info",
  important: "rich.callout_important",
};

export function FallbackMarkdown({ content }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const mdStyles = useMemo(() => makeMdStyles(theme), [theme]);
  const fenceStyles = useMemo(() => makeFenceStyles(theme), [theme]);
  const calloutStyles = useMemo(() => makeCalloutStyles(theme), [theme]);
  const rules = useMemo<RenderRules>(
    () => ({
      ...defaultRules,
      fence: (node: FenceNode) =>
        renderFallbackFence(node, fenceStyles, calloutStyles, t),
      code_block: (node: FenceNode) =>
        renderFallbackFence(node, fenceStyles, calloutStyles, t),
    }),
    [fenceStyles, calloutStyles, t],
  );
  const prepared = useMemo(() => preprocessMarkdown(content), [content]);

  return (
    <Markdown style={mdStyles} rules={rules} markdownit={markdownItInstance}>
      {prepared}
    </Markdown>
  );
}

function visualFallbackLabel(lang: string, content: string, t: (key: string) => string): string {
  const id = fenceIdForLang(lang);
  if (id === "chart") return t("rich.chart");
  if (id === "mermaid") return t(mermaidTitleKey(content));
  if (documentFormForLang(lang) === "molecule") return t("rich.chemistry_structure");
  if (id === "chem_scene") return t("rich.chemistry_diagram");
  return t("rich.diagram");
}

/**
 * One fence as this fallback draws it, for a block that failed on its own
 * (`FenceErrorBoundary`). A geometry or graph fence is the block that failed,
 * so it is named, not drawn again.
 */
export function FallbackFence({ lang, content }: { lang: string; content: string }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const fenceStyles = useMemo(() => makeFenceStyles(theme), [theme]);
  const calloutStyles = useMemo(() => makeCalloutStyles(theme), [theme]);
  const node = { key: "fallback", content, sourceInfo: lang };
  return renderFallbackFence(node, fenceStyles, calloutStyles, t, false);
}

function renderFallbackFence(
  node: FenceNode,
  fenceStyles: ReturnType<typeof makeFenceStyles>,
  calloutStyles: ReturnType<typeof makeCalloutStyles>,
  t: (key: string) => string,
  redrawDiagrams = true,
) {
  const found = classifyFallbackFence(node.sourceInfo, node.content);
  const classified =
    !redrawDiagrams && (found.kind === "geometry" || found.kind === "graph")
      ? { kind: "visual" as const, labelLang: node.sourceInfo ?? "", snippet: "" }
      : found;
  if (classified.kind === "callout") {
    if (!classified.body) return null;
    const i18nKey = CALLOUT_I18N_KEYS[classified.calloutKind] ?? "rich.callout_note";
    const label = t(i18nKey);
    return (
      <View key={node.key} style={calloutStyles.wrap}>
        <Text style={calloutStyles.label}>{label}</Text>
        <Text style={calloutStyles.body}>{classified.body}</Text>
      </View>
    );
  }
  if (classified.kind === "geometry") {
    return <LazyGeometryBlock key={node.key} content={classified.body} />;
  }
  if (classified.kind === "graph") {
    return <LazyFunctionGraphBlock key={node.key} content={classified.body} />;
  }
  if (classified.kind === "answer") {
    if (!classified.body) return null;
    return (
      <View key={node.key} style={calloutStyles.wrap}>
        <Text style={calloutStyles.body} selectable>
          {classified.body}
        </Text>
      </View>
    );
  }
  if (classified.kind === "sources" || classified.kind === "places") {
    if (classified.items.length === 0) return null;
    return (
      <View key={node.key} style={calloutStyles.wrap}>
        {classified.kind === "sources" ? (
          <Text style={calloutStyles.label}>{t("rich.source")}</Text>
        ) : null}
        {classified.items.map((item, index) => (
          <Text key={`${item.title}-${index}`} style={calloutStyles.body} selectable>
            {item.url ? `${item.title} (${item.url})` : item.title}
          </Text>
        ))}
      </View>
    );
  }
  if (classified.kind === "visual") {
    const label = visualFallbackLabel(classified.labelLang, node.content, t);
    return (
      <View key={node.key} style={calloutStyles.wrap}>
        <Text style={calloutStyles.label}>{label}</Text>
        {classified.snippet ? (
          <Text style={calloutStyles.body} selectable>
            {classified.snippet}
          </Text>
        ) : null}
      </View>
    );
  }
  if (!classified.code) return null;
  const languageLabel = codeLanguageLabel(classified.lang);
  return (
    <View key={node.key} style={fenceStyles.codeWrap}>
      {languageLabel ? <Text style={fenceStyles.lang}>{languageLabel}</Text> : null}
      <Text style={fenceStyles.code} selectable>
        {classified.code}
      </Text>
    </View>
  );
}

function makeMdStyles(t: Theme) {
  return StyleSheet.create({
    body: { ...Type.body, color: t.assistantText, lineHeight: 24 },
    code_inline: inlineCodeTextStyle(t),
    // The reply's heading ladder: never smaller than body text (h4–h6 were 15/14/13).
    heading1: { ...Type.h1, marginVertical: Space.xs, color: t.text },
    heading2: { ...Type.h2, marginVertical: Space.xs, color: t.text },
    heading3: { ...Type.h3, marginVertical: Space.xxs, color: t.text },
    heading4: { ...Type.h4, marginVertical: Space.xxs, color: t.text },
    heading5: { ...Type.h5, marginVertical: 2, color: t.text },
    heading6: { ...Type.h6, marginVertical: 2, color: t.text },
    strong: { ...Weight.bold },
    em: { ...Italic.regular },
    // Themed, so the library's light defaults (#F5F5F5 quote fill, #000 rules
    // and table lines) never show in dark mode.
    blockquote: {
      backgroundColor: "transparent",
      borderLeftWidth: 3,
      borderLeftColor: t.primary,
      paddingLeft: Space.sm,
      marginVertical: Space.xs,
    },
    hr: { backgroundColor: t.border, height: StyleSheet.hairlineWidth },
    table: { marginVertical: Space.xs, borderColor: t.border },
    tr: { borderColor: t.border },
    link: { color: t.primary, textDecorationLine: "underline" },
  });
}

function makeFenceStyles(t: Theme) {
  return StyleSheet.create({
    codeWrap: {
      backgroundColor: t.codeBg,
      borderRadius: Radius.sm,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      marginVertical: Space.xs,
      overflow: "hidden",
    },
    lang: {
      ...Type.meta,
      ...Weight.semibold,
      color: t.codeLang,
      paddingHorizontal: Space.sm,
      paddingTop: Space.xs,
    },
    code: {
      ...Type.compact,
      ...CODE_FACE,
      lineHeight: 20,
      color: t.text,
      padding: Space.sm,
    },
  });
}

function makeCalloutStyles(t: Theme) {
  return StyleSheet.create({
    wrap: {
      backgroundColor: t.contentSurface,
      borderLeftWidth: 3,
      borderLeftColor: t.primary,
      borderRadius: Radius.xs,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.sm,
      marginVertical: Space.xs,
    },
    label: {
      ...Type.overline,
      color: t.primary,
      marginBottom: Space.xxs,
    },
    body: { ...Type.callout, ...Weight.regular, color: t.text },
  });
}
