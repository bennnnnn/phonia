import { memo, useMemo } from "react";
import { Platform, Pressable, StyleSheet, Text, View, type TextStyle } from "react-native";

import { MATH_FONT, MATH_SIZE1_FONT, MATH_SYMBOL_FONT, MATH_VARIABLE_FONT } from "@/lib/fonts";
import { AMS_ONLY_CHARS, BLACKBOARD_LATIN, MATH_NOT_GLYPH } from "@/lib/math/glyphs";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Weight } from "@/lib/type";
import { Icon } from "@/ui/icons/Icon";
import type { IconName } from "@/ui/icons/names";
import { IconSize } from "@/ui/icons/sizes";

/**
 * Keys follow the reader's text size only a little. System keyboards do not
 * scale their keys at all; a key that grew with the text would wrap or clip.
 */
export const KEY_FONT_SCALE_MAX = 1.15;

/** Big operators: drawn in KaTeX_Size1, a little smaller than text. */
const BIG_OPERATORS = new Set(["∫", "∬", "∭", "∮", "∑", "∏"]);
const BIG_OPERATOR_SCALE = 0.8;
/** Symbols the app font (Source Sans 3) does not carry, but KaTeX_Main does. */
const MAIN_FACE_CHARS = new Set([
  "∇", "∠", "⊥", "∥", "≅", "∼", "∈", "⊂", "⊆", "∪", "⇔", "⌊", "⌋", "⌈", "⌉", "∅",
]);
const SCRIPT_SCALE = 0.62;
const SCRIPT_SHIFT = 0.42;

type Script = "base" | "sup" | "sub";
type Segment = { text: string; script: Script };
type Run = { text: string; family: string; scale: number; negated?: boolean };

/** `sin^{−1}` → sin + raised −1. */
export function keyLabelSegments(label: string): Segment[] {
  const out: Segment[] = [];
  let i = 0;
  let base = "";
  while (i < label.length) {
    const mark = label[i];
    if ((mark === "^" || mark === "_") && label[i + 1] === "{") {
      const close = label.indexOf("}", i + 2);
      if (close !== -1) {
        if (base) out.push({ text: base, script: "base" });
        base = "";
        out.push({ text: label.slice(i + 2, close), script: mark === "^" ? "sup" : "sub" });
        i = close + 1;
        continue;
      }
    }
    base += label[i];
    i += 1;
  }
  if (base) out.push({ text: base, script: "base" });
  return out;
}

const UI_FAMILY = Weight.semibold.fontFamily as string;

function faceFor(ch: string): { family: string; scale: number; text: string; negated?: boolean } {
  if (BIG_OPERATORS.has(ch)) return { family: MATH_SIZE1_FONT, scale: BIG_OPERATOR_SCALE, text: ch };
  if (BLACKBOARD_LATIN[ch]) return { family: MATH_SYMBOL_FONT, scale: 1, text: BLACKBOARD_LATIN[ch]! };
  if (AMS_ONLY_CHARS.has(ch)) return { family: MATH_SYMBOL_FONT, scale: 1, text: ch };
  if (MAIN_FACE_CHARS.has(ch)) return { family: MATH_FONT, scale: 1, text: ch };
  // ∉ is ∈ with KaTeX's negating slash laid over it.
  if (ch === "∉") return { family: MATH_FONT, scale: 1, text: "∈", negated: true };
  return { family: UI_FAMILY, scale: 1, text: ch };
}

/** Each glyph in a face that has it, so Android never falls back to Roboto. */
export function keyLabelRuns(text: string, variable: boolean): Run[] {
  if (variable) return [{ text, family: MATH_VARIABLE_FONT, scale: 1.1 }];
  const runs: Run[] = [];
  for (const ch of Array.from(text)) {
    const face = faceFor(ch);
    const last = runs[runs.length - 1];
    if (last && !face.negated && !last.negated && last.family === face.family && last.scale === face.scale) {
      last.text += face.text;
    } else {
      runs.push({ text: face.text, family: face.family, scale: face.scale, negated: face.negated });
    }
  }
  return runs;
}

/** Wider labels get a smaller face, so the widest one fits a 52pt key. */
export function keyLabelSize(segments: Segment[]): number {
  const units = segments.reduce(
    (sum, seg) => sum + Array.from(seg.text).length * (seg.script === "base" ? 1 : SCRIPT_SCALE),
    0,
  );
  if (units <= 1.5) return 20;
  if (units <= 2.5) return 18;
  if (units <= 3.5) return 17;
  if (units <= 4.5) return 15;
  return 14;
}

/** x, y, z are variables, set in math italic; e and i are constants and stay upright. */
const VARIABLE_LABEL = /^[xyz]$/;

function KeyLabel({ label, color }: { label: string; color: string }) {
  const segments = useMemo(() => keyLabelSegments(label), [label]);
  const size = keyLabelSize(segments);
  const variable = VARIABLE_LABEL.test(label);
  return (
    <View style={styles.labelRow} pointerEvents="none">
      {segments.map((seg, k) => {
        const segSize = seg.script === "base" ? size : Math.round(size * SCRIPT_SCALE);
        // Raise or lower a script by part of the base size, from the base's midline.
        const shift =
          seg.script === "sup"
            ? { marginBottom: size * SCRIPT_SHIFT }
            : seg.script === "sub"
              ? { marginTop: size * SCRIPT_SHIFT }
              : null;
        return (
          <View key={k} style={[styles.segment, shift]}>
            {keyLabelRuns(seg.text, variable).map((run, r) => (
              <RunText key={r} run={run} size={segSize} color={color} />
            ))}
          </View>
        );
      })}
    </View>
  );
}

function RunText({ run, size, color }: { run: Run; size: number; color: string }) {
  const fontSize = Math.round(size * run.scale);
  const face: TextStyle = {
    ...Weight.regular,
    // The file is already the weight we want; ask for its regular slot.
    fontFamily: run.family,
    fontSize,
    lineHeight: Math.round(fontSize * 1.25),
    color,
  };
  const text = (
    <Text
      style={[styles.text, face]}
      numberOfLines={1}
      maxFontSizeMultiplier={KEY_FONT_SCALE_MAX}
    >
      {run.text}
    </Text>
  );
  if (!run.negated) return text;
  return (
    <View>
      {text}
      <Text
        style={[styles.text, face, styles.notGlyph]}
        numberOfLines={1}
        maxFontSizeMultiplier={KEY_FONT_SCALE_MAX}
      >
        {MATH_NOT_GLYPH}
      </Text>
    </View>
  );
}

type Props = {
  /** Key face; `^{…}` / `_{…}` draw raised / lowered text. */
  label?: string;
  icon?: IconName;
  testID: string;
  accessibilityLabel: string;
  onPress: () => void;
  height: number;
  /** Keys a row is divided into; the converter's Ask key spans two. */
  span?: number;
};

/** One key for every page of the math pad, the converter included. */
export const MathKey = memo(function MathKey({
  label,
  icon,
  testID,
  accessibilityLabel,
  onPress,
  height,
  span = 1,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const ink = theme.text;
  return (
    <Pressable
      onPress={onPress}
      android_ripple={{ color: theme.pressed, foreground: true }}
      style={({ pressed }) => [
        s.key,
        { height, flex: span },
        Platform.OS === "ios" && pressed && s.pressed,
      ]}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      testID={testID}
    >
      {icon ? (
        <Icon name={icon} size={IconSize.sm} color={ink} testID={`${testID}-icon`} />
      ) : label ? (
        <KeyLabel label={label} color={ink} />
      ) : null}
    </Pressable>
  );
});

const styles = StyleSheet.create({
  labelRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: Space.xxs,
    maxWidth: "100%",
  },
  segment: { flexDirection: "row", alignItems: "center" },
  text: {
    textAlign: "center",
    ...(Platform.OS === "android" ? { includeFontPadding: false, textAlignVertical: "center" } : null),
  },
  notGlyph: { position: "absolute", left: 0, right: 0 },
});

const makeStyles = (theme: Theme) =>
  StyleSheet.create({
    key: {
      minHeight: Space.minTouch,
      borderRadius: Radius.xs,
      alignItems: "center",
      justifyContent: "center",
      overflow: "hidden",
      backgroundColor: theme.bg,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
    },
    pressed: { backgroundColor: theme.control },
  });
