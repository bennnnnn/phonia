import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";

import { ComparisonDraft } from "@/lib/richBlocks";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { PARAGRAPH_GAP } from "@/components/markdown/markdownContentStyles";

type Props = { data: ComparisonDraft };

export function ComparisonBlock({ data }: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);

  return (
    <View style={s.wrap}>
      <View style={s.row}>
        <View style={[s.col, s.leftCol]}>
          <Text style={s.heading}>{data.leftTitle}</Text>
          {data.left.map((item, i) => (
            <View key={`l-${i}`} style={s.itemRow}>
              <Text style={s.bullet}>+</Text>
              <Text style={s.item} selectable>
                {item}
              </Text>
            </View>
          ))}
        </View>
        <View style={s.divider} />
        <View style={[s.col, s.rightCol]}>
          <Text style={s.heading}>{data.rightTitle}</Text>
          {data.right.map((item, i) => (
            <View key={`r-${i}`} style={s.itemRow}>
              <Text style={[s.bullet, s.bulletNeg]}>−</Text>
              <Text style={s.item} selectable>
                {item}
              </Text>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    wrap: {
      alignSelf: "stretch",
      borderRadius: Radius.card,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      marginTop: 0,
      marginBottom: PARAGRAPH_GAP,
      overflow: "hidden",
    },
    row: { flexDirection: "row" },
    col: { flex: 1, padding: Space.sm, gap: Space.xs },
    leftCol: {},
    rightCol: {},
    divider: { width: StyleSheet.hairlineWidth, backgroundColor: t.border },
    heading: { ...Type.secondary, ...Weight.bold, color: t.text, marginBottom: Space.xxs },
    itemRow: { flexDirection: "row", gap: Space.xs, alignItems: "flex-start" },
    // The item's role, so the mark and the first line share one line box.
    bullet: { ...Type.callout, ...Weight.bold, color: t.success },
    bulletNeg: { color: t.danger },
    item: { flex: 1, ...Type.callout, ...Weight.regular, color: t.text },
  });
}
