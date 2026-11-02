import { useMemo } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import {
  inlineCodeTextStyle,
  PARAGRAPH_GAP,
} from "@/components/markdown/markdownContentStyles";
import { ChipText } from "@/components/rich/ChipText";
import { useFenceRefused } from "@/components/rich/useFenceRefused";
import { CODE_FACE } from "@/lib/fonts";
import i18n from "@/lib/i18n";
import { arrayBody, looseArrayValues } from "@/lib/lesson/cardBody";
import { arrayText, type LooseArray, formatCell } from "@/lib/lesson/lessonFences";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

type Props = { content: string };

// Up to this many boxes share the card's width; more scroll sideways.
const FIT_CELLS = 6;
/** A list is JSON: text in its place, or JSON the card cannot read, is a refused fence. */
const ARRAY_BODY = { json: true };

/**
 * A list as gray boxes, each value over its index, with the pair that matters
 * lit green: an optional line above, a result caption and a note below.
 */
export function ArrayBlock({ content }: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const body = useMemo(() => arrayBody(content), [content]);
  const fence = body?.kind === "card" ? body.card : null;
  useFenceRefused("array", content, body !== null && fence === null, ARRAY_BODY);

  if (!fence) {
    if (body?.kind === "plain") {
      return (
        <ChipText style={[s.note, s.plain]} chip={s.chip}>
          {body.text}
        </ChipText>
      );
    }
    return body?.kind === "loose" ? <LooseArrayText list={body.loose} s={s} /> : null;
  }

  const fits = fence.values.length <= FIT_CELLS;
  const cells = fence.values.map((value, index) => {
    const lit = fence.highlight.includes(index);
    return (
      <View
        key={index}
        style={[s.cell, fits ? s.cellFit : s.cellFixed, lit && s.cellLit]}
      >
        <Text
          style={[s.value, lit && s.lit]}
          numberOfLines={1}
          adjustsFontSizeToFit
        >
          {formatCell(value)}
        </Text>
        <Text style={[s.index, lit && s.lit]} numberOfLines={1}>
          {i18n.t("rich.array_index", { index })}
        </Text>
      </View>
    );
  });

  return (
    <View
      style={s.card}
      accessible
      accessibilityRole="image"
      accessibilityLabel={arrayText(fence)}
      testID="array-block"
    >
      {fence.title ? (
        <ChipText style={s.title} chip={s.chip}>
          {fence.title}
        </ChipText>
      ) : null}
      {fits ? (
        <View style={s.row}>{cells}</View>
      ) : (
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={s.row}>{cells}</View>
        </ScrollView>
      )}
      {fence.caption ? <Text style={s.caption}>{fence.caption}</Text> : null}
      {fence.note ? (
        <ChipText style={s.note} chip={s.chip}>
          {fence.note}
        </ChipText>
      ) : null}
    </View>
  );
}

/** A list whose fence did not parse: its lines and values as plain text. */
function LooseArrayText({ list, s }: { list: LooseArray; s: Styles }) {
  return (
    <View style={s.card} testID="array-block-text">
      {list.title ? (
        <ChipText style={s.title} chip={s.chip}>
          {list.title}
        </ChipText>
      ) : null}
      <Text style={s.values}>{looseArrayValues(list)}</Text>
      {list.caption ? <Text style={s.caption}>{list.caption}</Text> : null}
      {list.note ? (
        <ChipText style={s.note} chip={s.chip}>
          {list.note}
        </ChipText>
      ) : null}
    </View>
  );
}

type Styles = ReturnType<typeof makeStyles>;

function makeStyles(t: Theme) {
  return StyleSheet.create({
    card: {
      marginBottom: PARAGRAPH_GAP,
      padding: Space.md,
      gap: Space.md,
      borderRadius: Radius.menu,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      backgroundColor: t.bg,
    },
    row: { flexDirection: "row", gap: Space.xs },
    cell: {
      alignItems: "center",
      justifyContent: "center",
      gap: Space.xxs,
      paddingVertical: Space.sm,
      paddingHorizontal: Space.xxs,
      borderRadius: Radius.xl,
      backgroundColor: t.surface,
    },
    cellFit: { flex: 1, minWidth: 0 },
    cellFixed: { width: 72 },
    cellLit: { backgroundColor: t.successLight },
    value: { ...Type.title, ...Weight.bold, color: t.text },
    index: { ...Type.caption, color: t.textSecondary },
    lit: { color: t.success },
    title: { ...Type.body, color: t.textSecondary },
    caption: { ...Type.h3, ...Weight.bold, color: t.text, textAlign: "center" },
    note: { ...Type.body, color: t.text },
    chip: inlineCodeTextStyle(t),
    values: { ...Type.body, ...CODE_FACE, color: t.text },
    plain: { marginBottom: PARAGRAPH_GAP },
  });
}
