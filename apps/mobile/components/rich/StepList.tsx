import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";

import { RichBodyText } from "@/components/rich/RichBodyText";
import { Theme, useTheme } from "@/lib/theme";
import { DYNAMIC_TYPE_MAX, Type, Weight } from "@/lib/type";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { PARAGRAPH_GAP } from "@/components/markdown/markdownContentStyles";

type Props = { steps: string[] };

export function StepList({ steps }: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);

  return (
    <View style={s.wrap}>
      {steps.map((step, index) => (
        <View key={`step-${index}`} style={s.row}>
          <View style={s.badge}>
            <Text style={s.badgeText} maxFontSizeMultiplier={DYNAMIC_TYPE_MAX}>
              {index + 1}
            </Text>
          </View>
          <RichBodyText style={s.text} selectable>
            {step}
          </RichBodyText>
        </View>
      ))}
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    wrap: { marginTop: 0, marginBottom: PARAGRAPH_GAP, gap: Space.sm },
    row: {
      flexDirection: "row",
      gap: Space.sm,
      alignItems: "flex-start",
    },
    // Grows into a pill when large text makes the number wider than 24pt.
    badge: {
      minWidth: 24,
      minHeight: 24,
      paddingHorizontal: Space.xxs,
      borderRadius: Radius.md,
      backgroundColor: t.primaryLight,
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0,
      marginTop: 2,
    },
    badgeText: { ...Type.compact, ...Weight.bold, color: t.primary },
    text: { flex: 1, ...Type.body, color: t.text },
  });
}
