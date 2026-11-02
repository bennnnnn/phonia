import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { RichMathBody } from "@/components/rich/RichMathBody";
import { suggestionToSend, wrapSuggestionMath } from "@/features/suggestions/model/promptMath";
import { Theme, useTheme } from "@/lib/theme";
import { Space } from "@/lib/space";
import { Type } from "@/lib/type";
import { Icon } from "@/ui/icons/Icon";
import { IconSize } from "@/ui/icons/sizes";

type Props = {
  prompts: string[];
  onSelect: (prompt: string) => void;
};

/**
 * Follow-up questions under the latest reply: three tappable rows. Each has a
 * dotted underline under its words, the way a link reads, so it looks tappable
 * without a rule between rows.
 */
export function RelatedPromptLines({ prompts, onSelect }: Props) {
  const theme = useTheme();
  const s = makeStyles(theme);

  if (prompts.length === 0) return null;

  const lines = prompts
    .map((prompt) => suggestionToSend(prompt))
    .filter((prompt): prompt is string => prompt !== null)
    .slice(0, 3);
  if (lines.length === 0) return null;
  return (
    <View style={s.wrap}>
      {lines.map((prompt) => (
        <View key={prompt}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={prompt}
            onPress={() => onSelect(prompt)}
            style={({ pressed }) => [s.row, pressed && s.rowPressed]}
          >
            <Icon name="enter" size={IconSize.xs} color={theme.textTertiary} />
            <View style={s.body}>
              <View style={s.underlined}>
                <RichMathBody
                  content={wrapSuggestionMath(prompt)}
                  style={s.line}
                  textColor={theme.text}
                />
                <DottedUnderline color={theme.textTertiary} />
              </View>
            </View>
          </Pressable>
        </View>
      ))}
    </View>
  );
}

const DOT = 2;
const DOT_GAP = 3;

/** Round dots across the words' width. A dotted border on one side is not
 * drawn reliably on Android, so the dots are drawn as views. */
function DottedUnderline({ color }: { color: string }) {
  const [width, setWidth] = useState(0);
  const count = Math.max(0, Math.floor((width + DOT_GAP) / (DOT + DOT_GAP)));
  return (
    <View
      testID="related-prompt-underline"
      style={dots.row}
      onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
    >
      {Array.from({ length: count }, (_, i) => (
        <View key={i} style={[dots.dot, { backgroundColor: color }]} />
      ))}
    </View>
  );
}

const dots = StyleSheet.create({
  row: { flexDirection: "row", gap: DOT_GAP, height: DOT, marginTop: 2, overflow: "hidden" },
  dot: { width: DOT, height: DOT, borderRadius: DOT / 2 },
});

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    wrap: {
      marginHorizontal: Space.md,
      marginTop: Space.xs,
      marginBottom: Space.xs,
    },
    row: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
      minHeight: Space.minTouch,
      paddingVertical: Space.xs,
    },
    rowPressed: {
      backgroundColor: theme.pressed,
    },
    body: {
      flex: 1,
    },
    // As wide as the words, so the dots underline them and not the empty row.
    underlined: {
      alignSelf: "flex-start",
      maxWidth: "100%",
    },
    line: {
      ...Type.secondary,
      color: theme.text,
    },
  });
}
