import { useMemo, type ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Icon } from "@/ui/icons/Icon";

import { RichBodyText } from "@/components/rich/RichBodyText";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { IconSize } from "@/ui/icons/sizes";
import { PARAGRAPH_GAP, TRIM_TRAILING_GAP } from "@/components/markdown/markdownContentStyles";

type Props = { quote?: string; author?: string; children?: ReactNode; testID?: string };

export function QuoteBlock({ quote, author, children, testID }: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);

  return (
    <View style={s.wrap} testID={testID}>
      <Icon
        name="message-quote"
        size={IconSize.sm}
        color={theme.textTertiary}
        style={s.icon}
      />
      {children ? (
        <View style={TRIM_TRAILING_GAP}>{children}</View>
      ) : (
        <RichBodyText style={s.quote} selectable>
          {quote}
        </RichBodyText>
      )}
      {author ? <Text style={s.author}>— {author}</Text> : null}
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    wrap: {
      alignSelf: "stretch",
      backgroundColor: t.surface,
      // A full point, not a hairline: one device pixel of `border` vanished
      // against the page and the card read as loose text.
      borderWidth: 1,
      borderColor: t.border,
      borderRadius: Radius.card,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.sm,
      marginTop: 0,
      marginBottom: PARAGRAPH_GAP,
    },
    icon: { marginBottom: Space.xs },
    quote: { ...Type.body, color: t.text },
    author: {
      marginTop: Space.xs,
      ...Type.label,
      color: t.textSecondary,
    },
  });
}
