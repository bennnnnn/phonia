import { ReactNode, useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";

import type { TeachingSpec } from "@/lib/math/teachingBlock";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

const OBJECT_SIZE = 24;

/**
 * Objects to count for a small whole-number fact, one line per part of the
 * sum so the picture reads like it: `3` (start), `− 3` (taken away, crossed
 * out), `= 0` (left). The server sends the numbers and the object; this draws
 * them and never recomputes the fact.
 */
export function CountingPicture({ spec }: { spec: TeachingSpec }) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const first = Number(spec.first);
  const second = Number(spec.second);
  const result = Number(spec.result);
  const emoji = typeof spec.object === "string" ? spec.object : "●";

  const objects = (count: number, crossed = false) =>
    count === 0 ? (
      <View style={s.empty} testID="counting-empty" />
    ) : (
      Array.from({ length: count }, (_, i) => (
        <View
          key={i}
          style={s.objectCell}
          testID={crossed ? "counting-crossed" : "counting-object"}
        >
          <Text style={[s.object, crossed && s.faded]}>{emoji}</Text>
          {crossed ? <Text style={s.cross}>✕</Text> : null}
        </View>
      ))
    );

  const line = (label: string, content: ReactNode, testID: string) => (
    <View style={s.line} testID={testID}>
      <Text style={s.label}>{label}</Text>
      <View style={s.group}>{content}</View>
    </View>
  );

  switch (spec.operation) {
    case "add":
      return (
        <View style={s.lines}>
          {line(String(first), objects(first), "counting-start")}
          {line(`+ ${second}`, objects(second), "counting-change")}
          {line(`= ${result}`, objects(result), "counting-result")}
        </View>
      );
    case "subtract":
      return (
        <View style={s.lines}>
          {line(String(first), objects(first), "counting-start")}
          {line(`− ${second}`, objects(second, true), "counting-change")}
          {line(`= ${result}`, objects(result), "counting-result")}
        </View>
      );
    case "multiply":
      return (
        <View style={s.lines}>
          {line(
            `${first} × ${second}`,
            <View style={s.rows}>
              {Array.from({ length: first }, (_, row) => (
                <View key={row} style={s.row} testID="counting-row">
                  {objects(second)}
                </View>
              ))}
            </View>,
            "counting-start",
          )}
          <View style={s.line} testID="counting-result">
            <Text style={s.label}>{`= ${result}`}</Text>
          </View>
        </View>
      );
    default:
      return (
        <View style={s.lines}>
          {line(String(first), objects(first), "counting-start")}
          {line(
            `÷ ${second}`,
            <View style={s.groups}>
              {Array.from({ length: second }, (_, group) => (
                <View key={group} style={s.share} testID="counting-group">
                  {objects(result)}
                </View>
              ))}
            </View>,
            "counting-change",
          )}
          <View style={s.line} testID="counting-result">
            <Text style={s.label}>{`= ${result}`}</Text>
          </View>
        </View>
      );
  }
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    lines: { gap: Space.xs },
    line: { flexDirection: "row", alignItems: "center", gap: Space.sm },
    // Wide enough for "− 10" or "3 × 4", so every row of objects starts in one column.
    label: {
      ...Type.title,
      ...Weight.semibold,
      color: t.text,
      minWidth: 64,
      textAlign: "right",
    },
    group: {
      flexShrink: 1,
      flexDirection: "row",
      flexWrap: "wrap",
      alignItems: "center",
      gap: Space.xxs,
      minHeight: OBJECT_SIZE + 6,
    },
    rows: { gap: Space.xxs },
    row: { flexDirection: "row", flexWrap: "wrap", gap: Space.xxs },
    groups: { flexDirection: "row", flexWrap: "wrap", gap: Space.xs },
    share: {
      flexDirection: "row",
      flexWrap: "wrap",
      gap: Space.xxs,
      padding: Space.xxs,
      borderRadius: Radius.md,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
    },
    objectCell: {
      width: OBJECT_SIZE + 4,
      height: OBJECT_SIZE + 6,
      alignItems: "center",
      justifyContent: "center",
    },
    object: { fontSize: OBJECT_SIZE, lineHeight: OBJECT_SIZE + 6 },
    faded: { opacity: 0.35 },
    // A bold red ✕ over each taken-away object: "this one is gone".
    cross: {
      position: "absolute",
      fontSize: OBJECT_SIZE,
      lineHeight: OBJECT_SIZE + 6,
      color: t.danger,
      ...Weight.bold,
    },
    empty: { width: OBJECT_SIZE, height: OBJECT_SIZE + 6 },
  });
}
