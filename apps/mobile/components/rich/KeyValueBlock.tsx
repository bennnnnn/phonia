import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";

import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { PARAGRAPH_GAP } from "@/components/markdown/markdownContentStyles";

type Props = { rows: { key: string; value: string }[] };

export function KeyValueBlock({ rows }: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);

  return (
    <View style={s.wrap}>
      {rows.map((row, i) => (
        <View key={`${row.key}-${i}`} style={[s.row, i > 0 && s.rowBorder]}>
          <Text style={s.key}>{row.key}</Text>
          <Text style={s.value} selectable>
            {row.value || "—"}
          </Text>
        </View>
      ))}
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
      backgroundColor: t.bg,
      marginTop: 0,
      marginBottom: PARAGRAPH_GAP,
      overflow: "hidden",
    },
    row: {
      flexDirection: "row",
      gap: Space.sm,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.sm,
      // Key (14pt) and value (15pt) share a first baseline.
      alignItems: "baseline",
    },
    rowBorder: {
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: t.border,
    },
    key: {
      width: "38%",
      ...Type.label,
      color: t.textSecondary,
    },
    value: { flex: 1, ...Type.callout, ...Weight.regular, color: t.text },
  });
}
