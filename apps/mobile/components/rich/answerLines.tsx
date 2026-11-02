/** How an answer card lays out what does not fit one formula: a sentence, a long line. */
import { type ReactNode, useRef } from "react";
import {
  ScrollView,
  Text,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from "react-native";

import { DisplayRow, InlineFlow } from "@/components/markdown/rules/inlineFlow";
import { MathText } from "@/components/rich/MathText";
import { isHeavyInlineMath } from "@/lib/math/fenceRetag";
import { readableLatexFallback } from "@/lib/math/text";
import type { InlineMathPart } from "@/lib/markdown/inlineMath";
import { useTheme } from "@/lib/theme";

/**
 * One answer line wider than the card scrolls sideways. The scroll bar flashes
 * once the line is known to overflow, so its cut edge reads as more to see.
 */
export function ScrollingLine({
  testID,
  style,
  contentContainerStyle,
  children,
}: {
  testID: string;
  style: StyleProp<ViewStyle>;
  contentContainerStyle: StyleProp<ViewStyle>;
  children: ReactNode;
}) {
  const ref = useRef<ScrollView>(null);
  const seen = useRef({ viewport: 0, content: 0, flashed: false });
  const flashIfClipped = () => {
    const size = seen.current;
    if (size.flashed || size.viewport <= 0 || size.content <= size.viewport + 1) return;
    size.flashed = true;
    ref.current?.flashScrollIndicators();
  };
  return (
    <ScrollView
      ref={ref}
      testID={testID}
      horizontal
      nestedScrollEnabled
      showsHorizontalScrollIndicator
      persistentScrollbar
      bounces={false}
      style={style}
      contentContainerStyle={contentContainerStyle}
      onLayout={(event) => {
        seen.current.viewport = event.nativeEvent.layout.width;
        flashIfClipped();
      }}
      onContentSizeChange={(width) => {
        seen.current.content = width;
        flashIfClipped();
      }}
    >
      {children}
    </ScrollView>
  );
}

/** What a sentence answer says aloud: its words, and each formula read out. */
export function spokenAnswer(parts: InlineMathPart[]): string {
  return parts
    .map((part) => (part.type === "math" ? readableLatexFallback(part.value) : part.value))
    .join("");
}

/**
 * An answer written as a sentence ("a = g(sin θ − μ cos θ), which at 30° gives …"):
 * its words are text and its rows wrap at the card's edge instead of running off it.
 */
export function ProseAnswer({
  parts,
  textStyle,
  flowStyle,
  fontSize,
  children,
}: {
  parts: InlineMathPart[];
  textStyle: StyleProp<TextStyle>;
  flowStyle: StyleProp<ViewStyle>;
  fontSize: number;
  /** Drawn after the last word: the success check. */
  children?: ReactNode;
}) {
  const theme = useTheme();
  return (
    <InlineFlow testID="answer-prose" style={flowStyle}>
      {parts.map((part, i) => {
        if (part.type === "text") {
          return <Text key={i} style={textStyle} selectable>{part.value}</Text>;
        }
        return isHeavyInlineMath(part.value)
          ? <DisplayRow key={i} latex={part.value} />
          : <MathText key={i} latex={part.value} textColor={theme.text} fontSize={fontSize} />;
      })}
      {children}
    </InlineFlow>
  );
}
