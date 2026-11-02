import { useMemo } from "react";
import { ScrollView, StyleSheet, type StyleProp, type ViewStyle } from "react-native";
import RenderHtml, { defaultSystemFonts, type MixedStyleDeclaration } from "react-native-render-html";

import { CODE_FONT } from "@/lib/fonts";
import { htmlForInlinePreview } from "@/lib/preview/htmlForInlinePreview";
import { stripScripts } from "@/lib/preview/htmlScriptStrip";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import type { Theme } from "@/lib/theme";
import { Italic, Type, Weight } from "@/lib/type";
import { UI_FONT } from "@/lib/uiFont";

/**
 * The HTML preview where react-native-webview is missing: Expo Go. Development
 * builds only; HtmlPreviewModal loads it behind `__DEV__` (code-health audit DEAD-08).
 */

type PreviewStyles = {
  scroll: StyleProp<ViewStyle>;
  scrollContent: StyleProp<ViewStyle>;
  base: MixedStyleDeclaration;
};

// render-html drops any fontFamily not in this list, which turned every
// Source Sans role below back into the system font.
const PREVIEW_FONTS = [...defaultSystemFonts, ...Object.values(UI_FONT), CODE_FONT];

function makeTagStyles(theme: Theme) {
  return {
    body: { color: theme.text },
    p: { marginTop: 0, marginBottom: Space.sm },
    h1: { ...Type.display, marginBottom: Space.sm, color: theme.text },
    h2: { ...Type.h1, marginBottom: Space.sm, color: theme.text },
    h3: { ...Type.h2, marginBottom: Space.xs, color: theme.text },
    a: { color: theme.primary },
    // One file per weight: a bold or italic slot on the regular file draws
    // Roboto on Android and a faux face on iOS.
    b: Weight.bold,
    strong: Weight.bold,
    em: Italic.regular,
    i: Italic.regular,
    div: { color: theme.text },
    span: { color: theme.text },
    table: {
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
      marginVertical: Space.xs,
    },
    th: {
      backgroundColor: theme.surface,
      padding: Space.xs,
      ...Weight.bold,
    },
    td: { padding: Space.xs },
    pre: {
      backgroundColor: theme.codeBg,
      padding: Space.sm,
      borderRadius: Radius.xs,
      ...Type.meta,
      fontFamily: CODE_FONT,
      lineHeight: 18,
    },
    code: { ...Type.secondary, fontFamily: CODE_FONT },
    img: { marginVertical: Space.xs },
  };
}

export function StaticHtmlPreview({
  html,
  contentWidth,
  theme,
  styles: s,
}: {
  html: string;
  contentWidth: number;
  theme: Theme;
  styles: PreviewStyles;
}) {
  const previewHtml = useMemo(
    () => htmlForInlinePreview(stripScripts(html)),
    [html],
  );
  const tagStyles = useMemo(() => makeTagStyles(theme), [theme]);

  return (
    <ScrollView
      style={s.scroll}
      contentContainerStyle={s.scrollContent}
      showsVerticalScrollIndicator
    >
      <RenderHtml
        contentWidth={contentWidth}
        source={{ html: previewHtml }}
        baseStyle={s.base}
        tagsStyles={tagStyles}
        systemFonts={PREVIEW_FONTS}
      />
    </ScrollView>
  );
}
