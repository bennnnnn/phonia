import { useMemo } from "react";
import { StyleSheet, Text, View, type StyleProp, type TextStyle } from "react-native";

import { InlineCode } from "@/components/markdown/InlineCode";
import { inlineCodeTextStyle } from "@/components/markdown/markdownContentStyles";
import { MathText } from "@/components/rich/MathText";
import { MathBlock } from "@/components/rich/MathView";
import { RichBodyText } from "@/components/rich/RichBodyText";
import { isHeavyInlineMath } from "@/lib/math/fenceRetag";
import { parseRichMathText } from "@/lib/markdown/richMathText";
import { useTheme } from "@/lib/theme";
import { Italic, Weight } from "@/lib/type";

/** Math-aware callout text without invoking MarkdownContent or rich-fence routing. */
export function RichMathBody({
  content,
  style,
  textColor,
}: {
  content: string;
  style?: StyleProp<TextStyle>;
  textColor?: string;
}) {
  const theme = useTheme();
  const parts = useMemo(() => parseRichMathText(content), [content]);
  if (!parts.some((part) => part.type === "math")) {
    return <RichBodyText style={style} selectable>{content}</RichBodyText>;
  }
  return (
    <View style={styles.row} testID="rich-math-body">
      {parts.flatMap((part, index) => {
        if (part.type === "math") {
          return [isHeavyInlineMath(part.value)
            ? <MathBlock key={index} latex={part.value} />
            : <MathText key={index} latex={part.value} textColor={textColor ?? theme.text} />];
        }
        if (part.type === "code") {
          // One pill for the whole span, not a pill per word.
          return [
            <InlineCode key={index} style={[style, inlineCodeTextStyle(theme)]}>
              {part.value}
            </InlineCode>,
          ];
        }
        // Separate words can wrap around a sized fraction/radical. Never nest
        // those Views inside Text (iOS gives them a zero-sized attachment).
        return part.value.split(/(\n|[^\S\n]+)/).filter(Boolean).map((word, wordIndex) =>
          word === "\n" ? <View key={`${index}-${wordIndex}`} style={styles.break} /> : (
            <Text key={`${index}-${wordIndex}`} selectable style={[
              style,
              part.bold && styles.bold,
              part.italic && styles.italic,
            ]}>{word}</Text>
          ),
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", flexShrink: 1 },
  break: { width: "100%", height: 0 },
  bold: { ...Weight.bold },
  italic: { ...Italic.regular },
});
