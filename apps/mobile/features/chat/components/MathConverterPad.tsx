import { memo, useMemo, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { Icon } from "@/ui/icons/Icon";
import { useTranslation } from "react-i18next";

import { MathConverterUnitSheet } from "@/features/chat/components/MathConverterUnitSheet";
import { KEY_FONT_SCALE_MAX, MathKey } from "@/features/chat/components/MathKey";
import { selection as hapticSelection } from "@/lib/haptics";
import { PAD_GAP } from "@/lib/math/keyboardPad";
import { Space } from "@/lib/space";
import { Radius } from "@/lib/radius";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import {
  CONVERTER_DEFAULT_DIGITS,
  appendConverterDigit,
  convertUnit,
  converterAskText,
  defaultUnits,
  findUnit,
  formatConvertNumber,
  type UnitCategory,
} from "@/features/chat/model/unitConverter";
import { IconSize } from "@/ui/icons/sizes";

type Props = {
  keyHeight: number;
  onAsk: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
};

export const MathConverterPad = memo(function MathConverterPad({
  keyHeight,
  onAsk,
  onStop,
  streaming,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [category, setCategory] = useState<UnitCategory>("length");
  const [fromId, setFromId] = useState("m");
  const [toId, setToId] = useState("cm");
  const [digits, setDigits] = useState(CONVERTER_DEFAULT_DIGITS);
  const [fresh, setFresh] = useState(true);
  const [pickerFor, setPickerFor] = useState<"from" | "to" | null>(null);

  const from = findUnit(fromId);
  const to = findUnit(toId);
  const parsed = Number(digits);
  const raw = Number.isFinite(parsed) ? convertUnit(parsed, fromId, toId) : null;
  const result = raw == null ? "—" : formatConvertNumber(raw);

  const typeKey = (key: string) => {
    hapticSelection();
    const next = appendConverterDigit(digits, key, fresh);
    setDigits(next);
    setFresh(key === "AC" || (key === "back" && next === CONVERTER_DEFAULT_DIGITS));
  };

  const pickCategory = (next: UnitCategory) => {
    setCategory(next);
    const defaults = defaultUnits(next);
    setFromId(defaults.fromId);
    setToId(defaults.toId);
  };

  const pickUnit = (id: string) => {
    if (pickerFor === "from") setFromId(id);
    if (pickerFor === "to") setToId(id);
    setPickerFor(null);
  };

  // Send and Stop play their own haptic (the composer's send, the turn's stopped cue).
  const ask = () => {
    if (streaming) {
      onStop();
      return;
    }
    if (!from || !to) return;
    onAsk(converterAskText(digits, from.prompt, to.prompt));
  };

  return (
    <View style={s.wrap} testID="math-converter">
      <View style={[s.row, { height: keyHeight }]}>
        <Text
          style={s.value}
          numberOfLines={1}
          adjustsFontSizeToFit
          maxFontSizeMultiplier={KEY_FONT_SCALE_MAX}
          testID="math-converter-from-value"
        >
          {digits}
        </Text>
        <Pressable
          onPress={() => {
            hapticSelection();
            setFromId(toId);
            setToId(fromId);
            if (raw != null && Number.isFinite(raw)) {
              setDigits(formatConvertNumber(raw));
              setFresh(false);
            }
          }}
          style={({ pressed }) => [s.swap, pressed && s.swapPressed]}
          android_ripple={{ color: theme.pressed, borderless: true }}
          accessibilityRole="button"
          accessibilityLabel={t("chat.math_converter_swap")}
          testID="math-converter-swap"
        >
          <Icon name="swap" size={IconSize.sm} color={theme.primary} />
        </Pressable>
        <Text
          style={[s.value, s.valueOut]}
          numberOfLines={1}
          adjustsFontSizeToFit
          maxFontSizeMultiplier={KEY_FONT_SCALE_MAX}
          testID="math-converter-to-value"
        >
          {result}
        </Text>
      </View>
      <View style={[s.row, { height: keyHeight }]}>
        <UnitChip
          symbol={from?.symbol ?? ""}
          label={from?.prompt}
          testID="math-converter-from-unit"
          onPress={() => setPickerFor("from")}
          theme={theme}
          height={keyHeight}
        />
        <UnitChip
          symbol={to?.symbol ?? ""}
          label={to?.prompt}
          testID="math-converter-to-unit"
          onPress={() => setPickerFor("to")}
          theme={theme}
          height={keyHeight}
        />
      </View>
      {CONVERTER_PAD.map((row, r) => (
        <View key={r} style={s.row} testID={r === 0 ? "math-converter-numpad" : undefined}>
          {row.map((cell) =>
            cell === "ask" ? (
              <MathKey
                key={cell}
                label={streaming ? t("chat.stop") : t("chat.math_converter_ask")}
                accessibilityLabel={streaming ? t("chat.stop") : t("chat.math_converter_ask")}
                testID="math-converter-ask"
                onPress={ask}
                height={keyHeight}
                span={2}
              />
            ) : (
              <MathKey
                key={cell}
                label={cell === "back" ? undefined : cell === "AC" ? t("chat.math_converter_clear") : cell}
                icon={cell === "back" ? "backspace" : undefined}
                accessibilityLabel={
                  cell === "back"
                    ? t("chat.math_keyboard_backspace")
                    : cell === "AC"
                      ? t("chat.math_converter_clear")
                      : cell
                }
                testID={`math-converter-${cell === "back" ? "back" : cell === "." ? "dot" : cell}`}
                onPress={() => typeKey(cell)}
                height={keyHeight}
              />
            ),
          )}
        </View>
      ))}
      <MathConverterUnitSheet
        visible={pickerFor != null}
        category={category}
        selectedId={pickerFor === "to" ? toId : fromId}
        onClose={() => setPickerFor(null)}
        onPickCategory={pickCategory}
        onPickUnit={pickUnit}
      />
    </View>
  );
});

const CONVERTER_PAD = [
  ["7", "8", "9", "AC"],
  ["4", "5", "6", "back"],
  ["1", "2", "3", "±"],
  ["0", ".", "ask"],
] as const;

function UnitChip({
  symbol,
  label,
  testID,
  onPress,
  theme,
  height,
}: {
  symbol: string;
  label?: string;
  testID: string;
  onPress: () => void;
  theme: Theme;
  height: number;
}) {
  const s = useMemo(() => makeStyles(theme), [theme]);
  return (
    <Pressable
      onPress={onPress}
      android_ripple={{ color: theme.pressed, foreground: true }}
      style={({ pressed }) => [s.unitBtn, { height }, Platform.OS === "ios" && pressed && s.unitPressed]}
      accessibilityRole="button"
      accessibilityLabel={label ?? symbol}
      testID={testID}
    >
      <Text style={s.unitBtnLabel} numberOfLines={1} maxFontSizeMultiplier={KEY_FONT_SCALE_MAX}>
        {symbol}
      </Text>
      <Icon name="chevron-down" size={IconSize.xxs} color={theme.primary} />
    </Pressable>
  );
}

const makeStyles = (theme: Theme) =>
  StyleSheet.create({
    wrap: { gap: PAD_GAP },
    row: { flexDirection: "row", alignItems: "center", gap: PAD_GAP },
    value: {
      flex: 1,
      ...Type.title,
      color: theme.text,
      paddingHorizontal: Space.xxs,
    },
    valueOut: { color: theme.textSecondary, ...Weight.medium },
    unitBtn: {
      flex: 1,
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: Space.xxs,
      minHeight: Space.minTouch,
      paddingHorizontal: Space.sm,
      borderRadius: Radius.xs,
      overflow: "hidden",
      backgroundColor: theme.bg,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
    },
    unitPressed: { backgroundColor: theme.control },
    unitBtnLabel: { ...Type.callout, color: theme.text },
    swap: {
      minWidth: Space.minTouch,
      minHeight: Space.minTouch,
      alignItems: "center",
      justifyContent: "center",
      borderRadius: Radius.xs,
    },
    swapPressed: { opacity: 0.55 },
  });
