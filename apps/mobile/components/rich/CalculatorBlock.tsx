import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, Text, View } from "react-native";

import { useFenceRefused } from "@/components/rich/useFenceRefused";
import { VisualCard } from "@/components/rich/VisualCard";
import { formatCalendarDay } from "@/lib/datetime/format";
import appI18n from "@/lib/i18n";
import {
  askedValues,
  type Calculator,
  type CalculatorControl,
  parseCalculatorFence,
  readoutValues,
} from "@/lib/money/calculator";
import { calculatorPositions, saveCalculatorPositions } from "@/lib/money/calculatorPositions";
import { formatCalculatorValue } from "@/lib/money/format";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Button } from "@/ui/controls/Button";
import { Slider } from "@/ui/controls/Slider";

type Props = { content: string };

const FALLBACK_TITLE = "money.title.loan";
const CALCULATOR_BODY = { json: true };

/**
 * A loan, a card payoff or savings: a slider for each input and the numbers they give. The
 * server sends each number's formula as a checked tree; moving a slider re-evaluates it here,
 * and nothing is solved on the phone (docs/money.md). A body this app does not understand
 * draws nothing; the reply above it still states the numbers.
 */
export function CalculatorBlock({ content }: Props) {
  const calculator = useMemo(() => parseCalculatorFence(content), [content]);
  useFenceRefused("calculator", content, calculator === null, CALCULATOR_BODY);
  if (!calculator) return null;
  return <CalculatorCard key={content} content={content} calculator={calculator} />;
}

function CalculatorCard({ content, calculator }: { content: string; calculator: Calculator }) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const { t, i18n } = useTranslation();
  const locale = i18n?.language || appI18n.language || "en";
  const asked = useMemo(() => askedValues(calculator), [calculator]);
  const [values, setValues] = useState<Record<string, number>>(
    () => ({ ...asked, ...calculatorPositions(content) }),
  );
  const results = useMemo(() => readoutValues(calculator, values), [calculator, values]);
  const moved = calculator.controls.some((control) => values[control.name] !== asked[control.name]);

  // A key this app has no text for falls back, so a raw key never shows.
  const known = useCallback(
    (key: string | null, fallback: string) => (key && appI18n.exists(key) ? key : fallback),
    [],
  );
  const label = useCallback(
    (key: string | null, fallback = "") => (key && appI18n.exists(key) ? t(key) : fallback),
    [t],
  );
  const show = useCallback(
    (value: number, kind: CalculatorControl["format"]) =>
      formatCalculatorValue(value, kind, { locale, currency: calculator.currency, translate: t }),
    [calculator.currency, locale, t],
  );

  const setValue = useCallback(
    (name: string, value: number) =>
      setValues((current) => {
        const next = { ...current, [name]: value };
        saveCalculatorPositions(content, next);
        return next;
      }),
    [content],
  );
  const reset = useCallback(() => {
    saveCalculatorPositions(content, asked);
    setValues(asked);
  }, [asked, content]);

  const primary = calculator.readouts.find((readout) => readout.primary) ?? calculator.readouts[0]!;
  const others = calculator.readouts.filter((readout) => readout !== primary);
  const readoutText = (name: string, kind: CalculatorControl["format"], neverKey: string | null) => {
    const value = results[name];
    return value === null || value === undefined ? label(neverKey, "—") : show(value, kind);
  };
  const sourced = calculator.controls.find((control) => control.marker?.source)?.marker ?? null;
  const sourceDay = sourced?.asOf ? formatCalendarDay(sourced.asOf, "monthDayYear") : null;

  return (
    <VisualCard
      label={label(calculator.titleKey, t(FALLBACK_TITLE))}
      icon="calculator"
      headerRight={
        moved ? (
          <Button
            title={t("money.reset")}
            accessibilityLabel={t("money.reset_a11y")}
            onPress={reset}
            variant="ghost"
            size="sm"
            icon="refresh"
            testID="calculator-reset"
          />
        ) : null
      }
    >
      <View style={s.body} testID="calculator-card">
        <View style={s.primary} accessible accessibilityLiveRegion="polite">
          <Text style={s.primaryLabel}>{label(primary.labelKey)}</Text>
          <Text style={s.primaryValue} testID={`calculator-readout-${primary.name}`}>
            {readoutText(primary.name, primary.format, primary.neverKey)}
          </Text>
        </View>
        {others.length > 0 ? (
          <View style={s.others}>
            {others.map((readout) => (
              <View key={readout.name} style={s.other} accessible>
                <Text style={s.otherLabel}>{label(readout.labelKey)}</Text>
                <Text style={s.otherValue} testID={`calculator-readout-${readout.name}`}>
                  {readoutText(readout.name, readout.format, readout.neverKey)}
                </Text>
              </View>
            ))}
          </View>
        ) : null}
        <View style={s.controls}>
          {calculator.controls.map((control) => {
            const value = values[control.name] ?? control.value;
            const marker = control.marker;
            const markerValue = marker ? show(marker.value, control.format) : "";
            const markerDay = marker?.asOf ? formatCalendarDay(marker.asOf, "monthDay") : null;
            return (
              <Slider
                key={control.name}
                label={label(control.labelKey)}
                valueText={show(value, control.format)}
                value={value}
                min={control.min}
                max={control.max}
                step={control.step}
                onChange={(next) => setValue(control.name, next)}
                marker={
                  marker
                    ? {
                        value: marker.value,
                        label: markerDay
                          ? t(known(marker.labelKey, "money.average"), {
                              value: markerValue,
                              date: markerDay,
                            })
                          : t(known(`${marker.labelKey}_undated`, "money.average_undated"), {
                              value: markerValue,
                            }),
                        accessibilityLabel: markerDay
                          ? t("money.average_a11y", { value: markerValue, date: markerDay })
                          : t("money.average_a11y_undated", { value: markerValue }),
                      }
                    : null
                }
                testID={`calculator-slider-${control.name}`}
              />
            );
          })}
        </View>
        {sourced?.source ? (
          <Text style={s.source} testID="calculator-source">
            {sourceDay
              ? t("money.source", { source: sourced.source, date: sourceDay })
              : t("money.source_undated", { source: sourced.source })}
          </Text>
        ) : null}
      </View>
    </VisualCard>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    body: { padding: Space.md, gap: Space.md },
    primary: { gap: Space.xxs },
    primaryLabel: { ...Type.secondary, color: t.textSecondary },
    primaryValue: { ...Type.display, color: t.text, fontVariant: ["tabular-nums"] },
    others: { flexDirection: "row", flexWrap: "wrap", rowGap: Space.sm, columnGap: Space.lg },
    other: { gap: Space.xxs, minWidth: 120 },
    otherLabel: { ...Type.caption, color: t.textSecondary },
    otherValue: { ...Type.body, ...Weight.semibold, color: t.text, fontVariant: ["tabular-nums"] },
    controls: { gap: Space.sm },
    source: { ...Type.meta, color: t.textTertiary },
  });
}
