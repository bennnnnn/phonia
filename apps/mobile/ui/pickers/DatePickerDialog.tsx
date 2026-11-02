import { useEffect, useMemo, useRef, useState } from "react";
import {
  FlatList,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from "react-native-reanimated";
import { useTranslation } from "react-i18next";

import {
  addMonths,
  clampDay,
  dayOutOfRange,
  firstDayOfWeek,
  isSameDay,
  monthGrid,
  monthInRange,
  monthYearLabel,
  weekdayLabels,
  withDay,
  yearRange,
  type YearMonth,
} from "@/lib/datetime/calendarGrid";
import { formatDate, userWeekStart } from "@/lib/datetime/format";
import { selection } from "@/lib/haptics";
import { Motion, useReduceMotion } from "@/lib/motion";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { DYNAMIC_TYPE_PICKER_MAX, Type, Weight } from "@/lib/type";

import { IconButton } from "../controls/IconButton";
import { Icon } from "../icons/Icon";
import { IconSize } from "../icons/sizes";
import { Dialog } from "../overlay/Dialog";

const DATE_PICKER_WIDTH = 328;
const CELL = 40;
const YEAR_ROW = 52;
const SWIPE = 40;

type Props = {
  visible: boolean;
  /** The day to start from. Its time of day is kept in the result. */
  value: Date;
  onConfirm: (date: Date) => void;
  /** Cancel, scrim tap, or Android back. */
  onCancel: () => void;
  /** Earliest pickable day (time ignored). */
  minimumDate?: Date | null;
  /** Latest pickable day (time ignored). */
  maximumDate?: Date | null;
  /** Heading. Defaults to "Select date". */
  title?: string;
  testID?: string;
};

/**
 * Month calendar in a dialog: arrows or a sideways swipe change the month,
 * tapping "September 2026" opens the years. Today has a ring; days outside
 * min/max are greyed. Nothing changes until OK.
 */
export function DatePickerDialog({
  visible,
  value,
  onConfirm,
  onCancel,
  minimumDate,
  maximumDate,
  title,
  testID = "date-picker",
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const screen = useWindowDimensions();
  const reduceMotion = useReduceMotion();

  const [draft, setDraft] = useState(() => clampDay(value, minimumDate, maximumDate));
  const [shown, setShown] = useState<YearMonth>({ year: draft.getFullYear(), month: draft.getMonth() });
  const [years, setYears] = useState(false);
  const confirmed = useRef(false);
  const slide = useSharedValue(0);
  const fade = useSharedValue(1);

  useEffect(() => {
    if (!visible) return;
    confirmed.current = false;
    const start = clampDay(value, minimumDate, maximumDate);
    setDraft(start);
    setShown({ year: start.getFullYear(), month: start.getMonth() });
    setYears(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- open on the caller's value each time, not on the last draft
  }, [visible]);

  const cardWidth = Math.min(DATE_PICKER_WIDTH, screen.width - Space.lg * 2);
  const cell = Math.min(CELL, Math.floor((cardWidth - Space.lg * 2) / 7));
  // The phone's First Day of Week, which its clock reads again (a change re-renders this);
  // worked out once from the locale's region when the phone cannot say.
  const phoneWeekStart = userWeekStart();
  const weekStart = useMemo(() => phoneWeekStart ?? firstDayOfWeek(), [phoneWeekStart]);
  // Cached formatters: the 14 labels cost microseconds, and a change of language or
  // clock (a re-render) redraws them.
  const weekdays = weekdayLabels(weekStart);
  const weeks = useMemo(() => monthGrid(shown.year, shown.month, weekStart), [shown, weekStart]);
  const today = new Date();

  const canGo = (delta: number) => monthInRange(addMonths(shown, delta), minimumDate, maximumDate);

  const go = (delta: number) => {
    if (!canGo(delta)) return;
    selection();
    setShown((current) => addMonths(current, delta));
    if (!reduceMotion) {
      slide.value = delta * 24;
      fade.value = 0.3;
      slide.value = withTiming(0, { duration: Motion.duration.standard });
      fade.value = withTiming(1, { duration: Motion.duration.standard });
    }
  };

  const goRef = useRef(go);
  goRef.current = go;
  const swipe = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponderCapture: (_event, gesture) =>
          Math.abs(gesture.dx) > 12 && Math.abs(gesture.dx) > Math.abs(gesture.dy) * 1.5,
        onPanResponderRelease: (_event, gesture) => {
          if (gesture.dx <= -SWIPE) goRef.current(1);
          else if (gesture.dx >= SWIPE) goRef.current(-1);
        },
      }),
    [],
  );

  const monthStyle = useAnimatedStyle(() => ({
    opacity: fade.value,
    transform: [{ translateX: slide.value }],
  }));

  const pickYear = (year: number) => {
    selection();
    let month = shown.month;
    const min = minimumDate;
    const max = maximumDate;
    if (min && year === min.getFullYear()) month = Math.max(month, min.getMonth());
    if (max && year === max.getFullYear()) month = Math.min(month, max.getMonth());
    setShown({ year, month });
    setYears(false);
  };

  const handleClose = () => {
    if (!confirmed.current) onCancel();
  };

  const monthLabel = monthYearLabel(shown);

  return (
    <Dialog
      visible={visible}
      title={title ?? t("picker.select_date")}
      titleVariant="label"
      width={DATE_PICKER_WIDTH}
      onClose={handleClose}
      testID={testID}
      actions={[
        { label: t("common.cancel"), style: "cancel", testID: `${testID}-cancel` },
        {
          label: t("common.ok"),
          style: "primary",
          testID: `${testID}-ok`,
          onPress: () => {
            confirmed.current = true;
            onConfirm(draft);
          },
        },
      ]}
    >
      <Text style={s.headline} accessibilityLiveRegion="polite" testID={`${testID}-headline`}>
        {formatDate(draft, "weekdayDate")}
      </Text>
      <View style={s.divider} />

      <View style={s.monthRow}>
        <Pressable
          onPress={() => {
            selection();
            setYears((open) => !open);
          }}
          style={({ pressed }) => [s.monthButton, pressed && s.pressed]}
          accessibilityRole="button"
          accessibilityLabel={`${monthLabel}, ${t("picker.choose_year")}`}
          accessibilityState={{ expanded: years }}
          testID={`${testID}-years-toggle`}
        >
          <Text style={s.monthText}>{monthLabel}</Text>
          <Icon name={years ? "chevron-up" : "chevron-down"} size={IconSize.xs} color={theme.textSecondary} />
        </Pressable>
        {years ? null : (
          <View style={s.arrows}>
            <IconButton
              name="chevron-left"
              onPress={() => go(-1)}
              disabled={!canGo(-1)}
              color={theme.textSecondary}
              accessibilityLabel={t("picker.previous_month")}
              testID={`${testID}-previous`}
            />
            <IconButton
              name="chevron-right"
              onPress={() => go(1)}
              disabled={!canGo(1)}
              color={theme.textSecondary}
              accessibilityLabel={t("picker.next_month")}
              testID={`${testID}-next`}
            />
          </View>
        )}
      </View>

      <View style={{ height: cell * 7 }}>
        {years ? (
          <YearGrid
            selected={shown.year}
            current={today.getFullYear()}
            years={yearRange(shown.year, minimumDate, maximumDate)}
            onPick={pickYear}
            styles={s}
            testID={`${testID}-year`}
          />
        ) : (
          <Animated.View style={monthStyle} {...swipe.panHandlers} testID={`${testID}-month`}>
            <View style={s.week}>
              {weekdays.map((day, index) => (
                <View key={index} style={[s.cellBox, { width: cell, height: cell }]}>
                  <Text style={s.weekday} accessibilityLabel={day.long}>
                    {day.narrow}
                  </Text>
                </View>
              ))}
            </View>
            {weeks.map((week, row) => (
              <View key={row} style={s.week}>
                {week.map((day, column) => {
                  if (day == null) return <View key={column} style={{ width: cell, height: cell }} />;
                  const date = withDay(draft, shown, day);
                  const disabled = dayOutOfRange(date, minimumDate, maximumDate);
                  const selected = isSameDay(date, draft);
                  const isToday = isSameDay(date, today);
                  const spoken = formatDate(date, "fullDate");
                  return (
                    <Pressable
                      key={column}
                      onPress={() => {
                        selection();
                        setDraft(date);
                      }}
                      disabled={disabled}
                      style={[
                        s.day,
                        { width: cell, height: cell, borderRadius: cell / 2 },
                        isToday && !selected && s.dayToday,
                        selected && s.daySelected,
                      ]}
                      accessibilityRole="button"
                      accessibilityLabel={isToday ? `${t("picker.today")}, ${spoken}` : spoken}
                      accessibilityState={{ selected, disabled }}
                      testID={`${testID}-day-${day}`}
                    >
                      <Text
                        style={[
                          s.dayText,
                          isToday && s.dayTextToday,
                          selected && s.dayTextSelected,
                          disabled && s.dayTextDisabled,
                        ]}
                        maxFontSizeMultiplier={DYNAMIC_TYPE_PICKER_MAX}
                      >
                        {day}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            ))}
          </Animated.View>
        )}
      </View>
    </Dialog>
  );
}

function YearGrid({
  selected,
  current,
  years,
  onPick,
  styles: s,
  testID,
}: {
  selected: number;
  current: number;
  years: number[];
  onPick: (year: number) => void;
  styles: ReturnType<typeof makeStyles>;
  testID: string;
}) {
  const rows = useMemo(() => {
    const out: number[][] = [];
    for (let i = 0; i < years.length; i += 3) out.push(years.slice(i, i + 3));
    return out;
  }, [years]);
  const selectedRow = Math.max(0, rows.findIndex((row) => row.includes(selected)));

  return (
    <FlatList
      data={rows}
      keyExtractor={(row) => String(row[0])}
      getItemLayout={(_data, index) => ({ length: YEAR_ROW, offset: YEAR_ROW * index, index })}
      initialScrollIndex={Math.max(0, selectedRow - 2)}
      showsVerticalScrollIndicator={false}
      testID={`${testID}-list`}
      renderItem={({ item: row }) => (
        <View style={s.yearRow}>
          {row.map((year) => {
            const isSelected = year === selected;
            return (
              <Pressable
                key={year}
                onPress={() => onPick(year)}
                hitSlop={{ top: 4, bottom: 4 }}
                style={[s.year, year === current && !isSelected && s.yearCurrent, isSelected && s.yearSelected]}
                accessibilityRole="button"
                accessibilityState={{ selected: isSelected }}
                testID={`${testID}-${year}`}
              >
                <Text
                  style={[s.yearText, isSelected && s.yearTextSelected]}
                  maxFontSizeMultiplier={DYNAMIC_TYPE_PICKER_MAX}
                >
                  {year}
                </Text>
              </Pressable>
            );
          })}
        </View>
      )}
    />
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    headline: { ...Type.display, ...Weight.regular, color: t.text, marginTop: Space.xs },
    divider: {
      height: StyleSheet.hairlineWidth,
      backgroundColor: t.separator,
      marginHorizontal: -Space.lg,
      marginTop: Space.sm,
    },
    monthRow: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      marginTop: Space.xs,
      minHeight: Space.minTouch,
    },
    monthButton: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xxs,
      minHeight: Space.minTouch,
      paddingHorizontal: Space.xs,
      marginLeft: -Space.xs,
      borderRadius: Radius.full,
    },
    pressed: { backgroundColor: t.pressed },
    monthText: { ...Type.label, ...Weight.semibold, color: t.textSecondary },
    arrows: { flexDirection: "row", marginRight: -Space.sm },
    week: { flexDirection: "row", justifyContent: "space-between" },
    cellBox: { alignItems: "center", justifyContent: "center" },
    weekday: { ...Type.caption, color: t.textSecondary },
    day: { alignItems: "center", justifyContent: "center" },
    dayToday: { borderWidth: 1, borderColor: t.primary },
    daySelected: { backgroundColor: t.primary },
    dayText: { ...Type.secondary, color: t.text, fontVariant: ["tabular-nums"] },
    dayTextToday: { color: t.primary },
    dayTextSelected: { color: t.onPrimary, ...Weight.semibold },
    dayTextDisabled: { color: t.textDisabled, opacity: 0.6 },
    yearRow: { height: YEAR_ROW, flexDirection: "row", justifyContent: "space-around", alignItems: "center" },
    year: {
      width: 72,
      height: 36,
      borderRadius: Radius.full,
      alignItems: "center",
      justifyContent: "center",
    },
    yearCurrent: { borderWidth: 1, borderColor: t.primary },
    yearSelected: { backgroundColor: t.primary },
    yearText: { ...Type.secondary, color: t.text },
    yearTextSelected: { color: t.onPrimary, ...Weight.semibold },
  });
}
