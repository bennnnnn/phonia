import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";

import { CountingPicture } from "@/components/rich/CountingPicture";
import { MathText } from "@/components/rich/MathText";
import { spokenText } from "@/lib/markdown/plain";
import type { TeachingSpec } from "@/lib/math/teachingBlock";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    : [];
}

function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

export function TeachingCard({ spec }: { spec: TeachingSpec }) {
  const theme = useTheme();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  return (
    <View style={styles.card} accessibilityLabel={spokenText(spec.speech)} testID={`teaching-${spec.type}`}>
      <Picture spec={spec} styles={styles} />
    </View>
  );
}

function Picture({ spec, styles }: { spec: TeachingSpec; styles: ReturnType<typeof makeStyles> }) {
  switch (spec.type) {
    case "place_value":
      return <PlaceValue spec={spec} styles={styles} />;
    case "number_bond":
      return <Bond spec={spec} styles={styles} />;
    case "ten_frame":
      return <TenFrame spec={spec} styles={styles} />;
    case "array":
      return <ArrayPicture spec={spec} styles={styles} />;
    case "number_line_move":
      return <Move spec={spec} styles={styles} />;
    case "fraction_bar":
    case "fraction_line":
      return <FractionPicture spec={spec} styles={styles} />;
    case "decimal_compare":
    case "rounding":
      return <DecimalPicture spec={spec} styles={styles} />;
    case "polynomial_division":
      return <Division spec={spec} styles={styles} />;
    case "unit_circle":
      return <Circle spec={spec} styles={styles} />;
    case "box_plot":
      return <Box spec={spec} styles={styles} />;
    case "histogram":
      return <Histogram spec={spec} styles={styles} />;
    case "counting":
      return <CountingPicture spec={spec} />;
    default:
      return <Labeled spec={spec} styles={styles} />;
  }
}

function PlaceValue({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  const columns = records(spec.columns);
  return (
    <View>
      <View style={styles.row}>
        {columns.map((column, index) => (
          <View key={`${text(column.place)}-${index}`} style={styles.cell}>
            <Text style={styles.muted}>{text(column.place)}</Text>
            <Text style={styles.strong}>{text(column.digit)}</Text>
            <Text style={styles.muted}>{text(column.value)}</Text>
          </View>
        ))}
      </View>
      {spec.show_blocks ? (
        <Blocks hundreds={Number(spec.hundreds)} tens={Number(spec.tens)} ones={Number(spec.ones)} styles={styles} />
      ) : null}
      <Text style={styles.body}>{text(spec.expanded)}</Text>
    </View>
  );
}

function Blocks({
  hundreds,
  tens,
  ones,
  styles,
}: {
  hundreds: number;
  tens: number;
  ones: number;
  styles: Styles;
}) {
  return (
    <View style={styles.row} testID="base-ten-blocks">
      {Array.from({ length: hundreds }, (_, index) => (
        <View key={`h${index}`} style={styles.flat} />
      ))}
      {Array.from({ length: tens }, (_, index) => (
        <View key={`t${index}`} style={styles.rod} />
      ))}
      {Array.from({ length: ones }, (_, index) => (
        <View key={`o${index}`} style={styles.dot} />
      ))}
    </View>
  );
}

function Bond({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  return (
    <View style={styles.row}>
      <Text style={styles.strong}>{text(spec.left)}</Text>
      <Text style={styles.body}>+</Text>
      <Text style={styles.strong}>{text(spec.right)}</Text>
      <Text style={styles.body}>=</Text>
      <Text style={styles.strong}>{text(spec.whole)}</Text>
    </View>
  );
}

function TenFrame({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  const first = Number(spec.first);
  const fill = Number(spec.fill);
  const cells = Array.from({ length: 10 }, (_, index) => {
    if (index < first) return "first";
    if (index < first + fill) return "fill";
    return "empty";
  });
  return (
    <View>
      <View style={styles.frame}>
        {cells.map((kind, index) => (
          <View
            key={index}
            testID={`ten-cell-${kind}`}
            style={[
              styles.frameCell,
              kind === "first" && styles.filled,
              kind === "fill" && styles.added,
            ]}
          />
        ))}
      </View>
      <Text style={styles.body}>{`${text(spec.leftover)} left over`}</Text>
    </View>
  );
}

function ArrayPicture({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  const rows = Number(spec.rows);
  const columns = Number(spec.columns);
  return (
    <View testID="equal-groups">
      {Array.from({ length: rows }, (_, row) => (
        <View key={row} style={styles.row}>
          {Array.from({ length: columns }, (_, column) => (
            <View key={column} style={styles.dot} />
          ))}
        </View>
      ))}
    </View>
  );
}

function Move({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  const low = Number(spec.low);
  const high = Number(spec.high);
  const start = Number(spec.start);
  const end = Number(spec.end);
  const ticks = Array.from({ length: high - low + 1 }, (_, index) => low + index);
  return (
    <View style={styles.row}>
      {ticks.map((tick) => (
        <Text key={tick} style={tick === start || tick === end ? styles.strong : styles.muted}>
          {tick}
        </Text>
      ))}
    </View>
  );
}

function FractionPicture({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  if (spec.type === "fraction_line") {
    const slots = Number(spec.denominator);
    const mark = Number(spec.numerator);
    return (
      <View style={styles.row}>
        {Array.from({ length: slots + 1 }, (_, index) => (
          <Text key={index} style={index === mark ? styles.strong : styles.muted}>
            {index === mark ? text(spec.answer) : "|"}
          </Text>
        ))}
      </View>
    );
  }
  return (
    <View>
      {records(spec.rows).map((row, index) => (
        <View key={index} style={styles.row}>
          <Text style={styles.muted}>{text(row.label)}</Text>
          {Array.from({ length: Number(row.slots) }, (_, slot) => (
            <View key={slot} style={[styles.frameCell, slot < Number(row.filled) && styles.filled]} />
          ))}
        </View>
      ))}
    </View>
  );
}

function DecimalPicture({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  if (spec.type === "rounding") {
    return (
      <Text style={styles.body}>
        {`${text(spec.value)} → ${text(spec.rounded)} (${text(spec.place)}, round ${text(spec.direction)})`}
      </Text>
    );
  }
  const headers = Array.isArray(spec.headers) ? spec.headers.map(text) : [];
  return (
    <View>
      <Text style={styles.muted}>{headers.join(" | ")}</Text>
      <Text style={styles.body}>{(Array.isArray(spec.left_digits) ? spec.left_digits : []).join(" ")}</Text>
      <Text style={styles.body}>{(Array.isArray(spec.right_digits) ? spec.right_digits : []).join(" ")}</Text>
    </View>
  );
}

function Division({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  return (
    <View>
      <Text style={styles.body}>{`${text(spec.dividend)} ÷ ${text(spec.divisor)}`}</Text>
      <Text style={styles.body}>{`quotient ${text(spec.quotient)}, remainder ${text(spec.remainder)}`}</Text>
      {records(spec.steps).map((step, index) => (
        <Text key={index} style={styles.muted}>
          {`${text(step.term)} → ${text(step.remainder)}`}
        </Text>
      ))}
    </View>
  );
}

function Circle({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  const x = 54 + Number(spec.plot_x) * 46;
  const y = 54 - Number(spec.plot_y) * 46;
  return (
    <View>
      <View style={styles.circle}>
        <View style={[styles.dot, { left: x, top: y }]} />
      </View>
      {/* cos and sin arrive as TeX (`\frac{\sqrt{3}}{2}`): drawn as maths, never as source. */}
      <View style={styles.values}>
        <Text style={styles.body}>{`${text(spec.degrees)}°  cos `}</Text>
        <MathText latex={text(spec.cosine)} />
        <Text style={styles.body}>{"  sin "}</Text>
        <MathText latex={text(spec.sine)} />
      </View>
    </View>
  );
}

function Box({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  return (
    <Text style={styles.body} testID="box-plot-summary">
      {`${text(spec.minimum)} | ${text(spec.q1)} | ${text(spec.median)} | ${text(spec.q3)} | ${text(spec.maximum)}`}
    </Text>
  );
}

function Histogram({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  const bins = records(spec.bins);
  const tallest = Math.max(1, ...bins.map((bin) => Number(bin.count) || 0));
  return (
    <View style={styles.row}>
      {bins.map((bin, index) => (
        <View key={index} style={styles.barSlot}>
          <View style={[styles.bar, { height: 4 + (Number(bin.count) / tallest) * 48 }]} />
          <Text style={styles.muted}>{text(bin.label)}</Text>
        </View>
      ))}
    </View>
  );
}

function Labeled({ spec, styles }: { spec: TeachingSpec; styles: Styles }) {
  return <Text style={styles.body}>{spec.speech}</Text>;
}

type Styles = ReturnType<typeof makeStyles>;

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    card: {
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
      borderRadius: Radius.md,
      padding: Space.sm,
      gap: Space.xs,
    },
    row: { flexDirection: "row", flexWrap: "wrap", alignItems: "flex-end", gap: Space.xs },
    values: { flexDirection: "row", flexWrap: "wrap", alignItems: "center" },
    cell: { minWidth: 52, alignItems: "center" },
    body: { color: theme.text, ...Type.body },
    strong: { color: theme.text, ...Type.body, ...Weight.semibold },
    muted: { color: theme.textSecondary, ...Type.caption },
    flat: { width: 18, height: 18, backgroundColor: theme.accent, borderRadius: 2 },
    rod: { width: 6, height: 18, backgroundColor: theme.accent, borderRadius: 2 },
    dot: { width: 8, height: 8, borderRadius: Radius.row, backgroundColor: theme.accent },
    frame: { width: 180, flexDirection: "row", flexWrap: "wrap" },
    frameCell: {
      width: 28,
      height: 28,
      margin: 2,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
      borderRadius: Radius.row,
    },
    filled: { backgroundColor: theme.accent },
    added: { backgroundColor: theme.textSecondary },
    circle: {
      width: 112,
      height: 112,
      borderRadius: Radius.full,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.text,
    },
    barSlot: { alignItems: "center", width: 18 },
    bar: { width: 12, backgroundColor: theme.accent, borderRadius: 2 },
  });
}
