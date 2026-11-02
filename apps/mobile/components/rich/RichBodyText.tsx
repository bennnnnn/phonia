import { useMemo } from "react";
import { Text, type TextProps } from "react-native";

import { InlineCode } from "@/components/markdown/InlineCode";
import { inlineCodeTextStyle } from "@/components/markdown/markdownContentStyles";
import { parseInlineMarkdown } from "@/lib/markdown/inlineMarkdown";
import { useTheme } from "@/lib/theme";
import { Italic, Weight } from "@/lib/type";

/**
 * Renders a rich-fence body string with minimal inline markdown (bold, italic,
 * inline code) without invoking the full MarkdownContent pipeline (avoids
 * heavy re-processing and recursive rich-fence routing inside a fence body).
 */
export function RichBodyText(props: TextProps) {
  const { children, style, ...rest } = props;
  const theme = useTheme();
  const text = typeof children === "string" ? children : "";
  const tokens = useMemo(() => parseInlineMarkdown(text), [text]);

  if (tokens.length === 0) {
    return (
      <Text style={style} {...rest}>
        {text}
      </Text>
    );
  }

  return (
    <Text style={style} {...rest}>
      {tokens.map((token, i) => {
        if (token.type === "bold") {
          return (
            <Text key={i} style={{ ...Weight.bold }}>
              {token.value}
            </Text>
          );
        }
        if (token.type === "italic") {
          return (
            <Text key={i} style={Italic.regular}>
              {token.value}
            </Text>
          );
        }
        if (token.type === "code") {
          return (
            <InlineCode key={i} style={inlineCodeTextStyle(theme)}>
              {token.value}
            </InlineCode>
          );
        }
        return <Text key={i}>{token.value}</Text>;
      })}
    </Text>
  );
}
