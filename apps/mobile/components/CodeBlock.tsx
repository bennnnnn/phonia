import { memo, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, ScrollView, StyleSheet, Text, type TextStyle, View } from "react-native";

import {
  codeLanguageLabel,
  diffLineKinds,
  type DiffLineKind,
  fenceUsesSyntaxColor,
  groupTokensByLine,
  type HighlightToken,
  isDiffFence,
  parseFenceLang,
  resolveTokenColor,
  TOKEN_COLORS,
} from "@/lib/codeHighlight";
import type * as CodeTokenizeModule from "@/lib/codeTokenize";
import { Radius } from "@/lib/radius";
import { Theme, useTheme, withAlpha } from "@/lib/theme";

import { CopyButton } from "@/components/CopyButton";

import { CODE_FACE } from "@/lib/fonts";
import { Space } from "@/lib/space";
import { Type, Weight } from "@/lib/type";
import { PARAGRAPH_GAP } from "@/components/markdown/markdownContentStyles";
const CODE_FONT_SIZE = 13;
const CODE_LINE_HEIGHT = 20;

// Prism (~47 grammars registered at module load) is only pulled in once a
// code fence actually needs tokenizing, not on every message render — see
// lib/codeTokenize.ts. Cached at module scope so only the very first
// CodeBlock in a session pays the async-import cost; every one after it
// gets the module synchronously on initial render.
let cachedTokenizer: typeof CodeTokenizeModule | null = null;

function useCodeTokenizer(enabled: boolean): typeof CodeTokenizeModule | null {
  const [tokenizer, setTokenizer] = useState(enabled ? cachedTokenizer : null);
  useEffect(() => {
    if (!enabled) {
      setTokenizer(null);
      return;
    }
    if (cachedTokenizer) {
      setTokenizer(cachedTokenizer);
      return;
    }
    let cancelled = false;
    void import("@/lib/codeTokenize").then((mod) => {
      cachedTokenizer = mod;
      if (!cancelled) setTokenizer(mod);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled]);
  return tokenizer;
}

// One style object per ink, shared by every token drawn in it: a long block
// would otherwise build one per token on every render.
const tokenStyles = new Map<string, TextStyle>();

function tokenStyle(color: string): TextStyle {
  let style = tokenStyles.get(color);
  if (!style) {
    style = { ...CODE_FACE, fontSize: CODE_FONT_SIZE, lineHeight: CODE_LINE_HEIGHT, color };
    tokenStyles.set(color, style);
  }
  return style;
}

/**
 * A diff line's ink and tint: added lines on a green band, removed on a red
 * one, hunks and file headers muted. The changed lines keep body ink: green
 * or red ink on its own band read under AA in light mode (3.75 and 3.90:1).
 */
function diffLineStyle(kind: DiffLineKind, t: Theme): { color: string; backgroundColor?: string } | null {
  if (kind === "added") return { color: t.text, backgroundColor: withAlpha(t.success, 0.12) };
  if (kind === "removed") return { color: t.text, backgroundColor: withAlpha(t.danger, 0.1) };
  if (kind === "hunk" || kind === "header") return { color: t.textSecondary };
  return null;
}

function diffLineStyles(code: string, t: Theme) {
  return diffLineKinds(code.split("\n")).map((kind) => diffLineStyle(kind, t));
}

const CODE_COLLAPSED_LINES = 14;
/** Only fold code blocks with at least this many lines. */
const CODE_COLLAPSE_MIN_LINES = 18;
/** Room at the end of each line before the corner actions are measured: one copy button. */
const ACTIONS_GUTTER = 40;

export function CodeBlock({
  code,
  lang,
  headerExtra,
  footerExtra,
  showCopy = true,
  /** Open-fence stream: plain monospace, no Prism / copy / collapse. */
  streaming = false,
}: {
  code: string;
  lang: string;
  headerExtra?: ReactNode;
  footerExtra?: ReactNode;
  /** Math/diagram fences must not show a Copy affordance. */
  showCopy?: boolean;
  streaming?: boolean;
}) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const s = useMemo(() => makeStyles(t), [t]);
  const [expanded, setExpanded] = useState(false);
  // The corner holds copy plus any extras (HTML adds a 44 pt preview button),
  // so the line gutter follows the measured width, not one button's.
  const [actionsWidth, setActionsWidth] = useState(0);
  const fenceLang = parseFenceLang(lang);
  const languageLabel = codeLanguageLabel(lang);
  // A diff colors whole lines (added, removed), not Prism tokens.
  const diff = isDiffFence(lang) && !streaming;
  const colorSyntax = fenceUsesSyntaxColor(lang) && !diff;
  const tokenizer = useCodeTokenizer(!streaming && colorSyntax);
  const tokens = useMemo(() => {
    // While the fence is still open, skip Prism — retokenizing a growing
    // body every ~48ms is the jank the open-fence stream path avoids.
    // Untagged / teaching fences stay plain too: guessing a grammar paints
    // random words and there is no language to name.
    if (streaming || !colorSyntax || !tokenizer) return [{ text: code, color: TOKEN_COLORS.plain }];
    try {
      return tokenizer.tokenize(code, fenceLang);
    } catch {
      return [{ text: code, color: TOKEN_COLORS.plain }];
    }
  }, [streaming, colorSyntax, tokenizer, code, fenceLang]);
  const lines = useMemo(() => groupTokensByLine(tokens), [tokens]);
  const diffStyles = useMemo(() => (diff ? diffLineStyles(code, t) : null), [diff, code, t]);
  const lineCount = code.split("\n").length;
  const collapsible = !streaming && lineCount >= CODE_COLLAPSE_MIN_LINES;
  const collapsed = collapsible && !expanded;
  const copyEnabled = showCopy && !streaming;
  const hasActions = copyEnabled || Boolean(headerExtra);

  // Syntax colors are saturated mid-tones that read on either background, but
  // the near-black "plain" color is invisible on a dark panel — remap it.
  const colorFor = useCallback((c: string) => resolveTokenColor(c, t.isDark), [t.isDark]);
  // Folded, the card shows CODE_COLLAPSED_LINES and the top of the next; the
  // rest mount only when it opens.
  const shownLines = collapsed ? lines.slice(0, CODE_COLLAPSED_LINES + 1) : lines;

  return (
    // Tagged fences name the language in the top corner. Teaching fences
    // (no language, or ```text) stay a plain card — copy only.
    <View style={s.wrap}>
      {languageLabel ? (
        <Text
          style={[
            s.lang,
            hasActions && { paddingRight: Space.md + (actionsWidth || ACTIONS_GUTTER) },
          ]}
          testID="code-block-lang"
          numberOfLines={1}
        >
          {languageLabel}
        </Text>
      ) : null}
      <View
        style={[
          s.codeBody,
          collapsed && {
            maxHeight: CODE_LINE_HEIGHT * CODE_COLLAPSED_LINES + 24,
          },
        ]}
      >
        <ScrollView
          testID="code-block-scroll"
          horizontal
          showsHorizontalScrollIndicator={false}
          nestedScrollEnabled
          directionalLockEnabled
          style={s.codeScroller}
          contentContainerStyle={[s.codeScrollContent, diff && s.fill]}
        >
          <View
            testID="code-block-lines"
            style={[
              s.codeLines,
              // A tinted line runs to the card's edge, not to its last character.
              diff && s.fill,
              languageLabel != null && { paddingTop: Space.xs },
              hasActions && { paddingRight: Space.md + (actionsWidth || ACTIONS_GUTTER) },
            ]}
          >
            {shownLines.map((lineTokens, lineIdx) => (
              <CodeLine
                key={lineIdx}
                tokens={lineTokens}
                diffLine={diffStyles?.[lineIdx] ?? null}
                colorFor={colorFor}
                styles={s}
              />
            ))}
          </View>
        </ScrollView>
      </View>
      {hasActions ? (
        <View
          style={s.actions}
          testID="code-block-actions"
          onLayout={(e) => setActionsWidth(Math.ceil(e.nativeEvent.layout.width))}
        >
          {headerExtra}
          {copyEnabled ? <CopyButton text={code} /> : null}
        </View>
      ) : null}
      {collapsible && (
        <Pressable
          style={s.expandBtn}
          onPress={() => setExpanded((v) => !v)}
          // The bar is about 31pt tall; 8pt above and below make 44.
          hitSlop={Space.xs}
          accessibilityRole="button"
          accessibilityLabel={expanded ? tr("common.show_less") : tr("common.show_more")}
        >
          <Text style={s.expandText}>{expanded ? tr("common.show_less") : tr("common.show_more")}</Text>
        </Pressable>
      )}
      {footerExtra ? <View style={s.footer}>{footerExtra}</View> : null}
    </View>
  );
}

type CodeLineProps = {
  tokens: HighlightToken[];
  diffLine: ReturnType<typeof diffLineStyle>;
  colorFor: (color: string) => string;
  styles: ReturnType<typeof makeStyles>;
};

/**
 * Same tokens, same line. An open fence regroups its lines on every flush, so
 * the arrays are new each time; only the line still being written draws again.
 */
function sameCodeLine(prev: CodeLineProps, next: CodeLineProps): boolean {
  return (
    prev.diffLine === next.diffLine &&
    prev.colorFor === next.colorFor &&
    prev.styles === next.styles &&
    (prev.tokens === next.tokens ||
      (prev.tokens.length === next.tokens.length &&
        prev.tokens.every(
          (token, i) => token.text === next.tokens[i].text && token.color === next.tokens[i].color,
        )))
  );
}

/** One line: its tokens, or the whole line in its diff color on a tinted band. */
const CodeLine = memo(function CodeLine({
  tokens,
  diffLine,
  colorFor,
  styles: s,
}: CodeLineProps) {
  return (
    <View
      testID={diffLine ? "code-block-diff-line" : undefined}
      style={[
        s.codeLineRow,
        diffLine?.backgroundColor ? [s.diffRow, { backgroundColor: diffLine.backgroundColor }] : null,
      ]}
    >
      {tokens.length > 0 ? (
        tokens.map((tk, i) => (
          <Text key={i} style={tokenStyle(diffLine?.color ?? colorFor(tk.color))} selectable>
            {tk.text}
          </Text>
        ))
      ) : (
        <Text style={tokenStyle(colorFor(TOKEN_COLORS.plain))}> </Text>
      )}
    </View>
  );
}, sameCodeLine);

function makeStyles(t: Theme) {
  return StyleSheet.create({
    wrap: {
      alignSelf: "stretch",
      width: "100%",
      maxWidth: "100%",
      backgroundColor: t.codeBg,
      borderRadius: Radius.card,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      overflow: "hidden",
      marginTop: 0,
      marginBottom: PARAGRAPH_GAP,
    },
    lang: {
      ...Type.meta,
      ...Weight.semibold,
      color: t.codeLang,
      paddingTop: Space.xs,
      paddingLeft: Space.md,
      paddingRight: Space.md,
    },
    actions: {
      position: "absolute",
      top: Space.xs,
      right: Space.xs,
      zIndex: 3,
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      borderRadius: Radius.xs,
      // Masks a long first line that scrolls under the buttons.
      backgroundColor: t.codeBg,
    },
    codeBody: {
      overflow: "hidden",
      backgroundColor: t.codeBg,
      width: "100%",
      maxWidth: "100%",
      minWidth: 0,
    },
    codeScroller: { width: "100%", maxWidth: "100%", minWidth: 0 },
    codeScrollContent: { flexGrow: 0 },
    codeLines: {
      paddingVertical: Space.md,
      paddingHorizontal: Space.md,
      alignSelf: "flex-start",
    },
    codeLineRow: { flexDirection: "row", flexWrap: "nowrap", alignItems: "flex-start" },
    // The tint bleeds into the side padding so a changed line reads as a band.
    diffRow: { marginHorizontal: -Space.md, paddingHorizontal: Space.md },
    fill: { flexGrow: 1 },
    expandBtn: {
      alignItems: "center",
      paddingVertical: Space.xs,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: t.border,
      backgroundColor: t.codeBg,
    },
    expandText: { ...Type.meta, ...Weight.semibold, color: t.textSecondary },
    footer: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "flex-end",
      gap: Space.xxs,
      paddingHorizontal: Space.xs,
      paddingVertical: Space.xs,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: t.border,
      backgroundColor: t.surface,
    },
  });
}
