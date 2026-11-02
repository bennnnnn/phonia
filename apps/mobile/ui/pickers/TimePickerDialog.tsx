import { useEffect, useMemo, useRef, useState } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";

import {
  dayPeriodLabels,
  from12Hour,
  hourLabel,
  minutesFromTime,
  pad2,
  parseHourInput,
  parseMinuteInput,
  withDayHalf,
  type ClockMode,
  type TimeOfDay,
} from "@/lib/datetime/clockDial";
import { formatMinuteOfDay, userUses24HourClock } from "@/lib/datetime/format";
import { selection } from "@/lib/haptics";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { DYNAMIC_TYPE_PICKER_MAX, Type, Weight } from "@/lib/type";
import { UI_LINE_EM } from "@/lib/uiFont";

import { IconButton } from "../controls/IconButton";
import { IconSize } from "../icons/sizes";
import { Dialog } from "../overlay/Dialog";
import { CLOCK_DIAL_SIZE, ClockDial } from "./ClockDial";

/** Material time picker: 328 wide, so the 256 dial and 96 boxes fit inside 24 padding. */
const TIME_PICKER_WIDTH = 328;
const PERIOD_WIDTH = 52;
const COLON_WIDTH = 24;
const READOUT_HEIGHT = 80;

/**
 * The readout's height: 80, or one line of the capped clock digits once larger
 * text makes that taller (56pt × 1.3 × 1.424 em ≈ 104 at the cap).
 */
function readoutHeight(fontScale: number): number {
  const scale = Math.min(Math.max(fontScale, 1), DYNAMIC_TYPE_PICKER_MAX);
  return Math.max(READOUT_HEIGHT, Math.ceil(Type.clock.fontSize * scale * UI_LINE_EM));
}

type Props = {
  visible: boolean;
  /** The time to start from (24-hour). */
  value: TimeOfDay;
  onConfirm: (value: TimeOfDay) => void;
  /** Cancel, scrim tap, or Android back. */
  onCancel: () => void;
  /** Heading. Defaults to "Select time". */
  title?: string;
  /** Force a 12- or 24-hour clock. Defaults to the phone's setting, as times are formatted. */
  is24Hour?: boolean;
  testID?: string;
};

/**
 * The Android clock time picker, everywhere: big hour and minute boxes, AM/PM,
 * and a dial you tap or drag. Picking the hour moves on to the minutes. The
 * keyboard button switches to typing the time. Nothing changes until OK.
 */
export function TimePickerDialog({
  visible,
  value,
  onConfirm,
  onCancel,
  title,
  is24Hour: forced24Hour,
  testID = "time-picker",
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const screen = useWindowDimensions();
  const is24Hour = forced24Hour ?? userUses24HourClock();
  const periods = dayPeriodLabels();

  const [draft, setDraft] = useState<TimeOfDay>(value);
  const [mode, setMode] = useState<ClockMode>("hour");
  const [typing, setTyping] = useState(false);
  const [hourText, setHourText] = useState("");
  const [minuteText, setMinuteText] = useState("");
  const [focused, setFocused] = useState<ClockMode | null>(null);
  const confirmed = useRef(false);

  useEffect(() => {
    if (!visible) return;
    confirmed.current = false;
    setDraft(value);
    setMode("hour");
    setTyping(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- open on the caller's value each time, not on the last draft
  }, [visible]);

  const cardWidth = Math.min(TIME_PICKER_WIDTH, screen.width - Space.lg * 2);
  const contentWidth = cardWidth - Space.lg * 2;
  const dialSize = Math.min(CLOCK_DIAL_SIZE, contentWidth);
  const boxWidth = Math.floor(
    (contentWidth - COLON_WIDTH - (is24Hour ? 0 : PERIOD_WIDTH + Space.sm)) / 2,
  );
  const boxHeight = readoutHeight(screen.fontScale);

  const pm = draft.hour >= 12;
  const typedHour = parseHourInput(hourText, is24Hour);
  const typedMinute = parseMinuteInput(minuteText);
  const typedValid = typedHour != null && typedMinute != null;
  const typed: TimeOfDay | null = typedValid
    ? { hour: is24Hour ? typedHour : from12Hour(typedHour, pm), minute: typedMinute }
    : null;
  const result = typing ? typed : draft;

  const startTyping = () => {
    setHourText(hourLabel(draft.hour, is24Hour));
    setMinuteText(pad2(draft.minute));
    setTyping(true);
  };
  const stopTyping = () => {
    if (typed) setDraft(typed);
    setTyping(false);
    setMode("hour");
  };

  const setPeriod = (nextPm: boolean) => {
    if (nextPm === pm) return;
    selection();
    setDraft((current) => ({ ...current, hour: withDayHalf(current.hour, nextPm) }));
  };

  const spokenTime = formatMinuteOfDay(minutesFromTime(draft), is24Hour ? "h23" : "h12");

  const handleClose = () => {
    if (!confirmed.current) onCancel();
  };

  const readoutBox = (part: ClockMode) => {
    const active = typing ? focused === part : mode === part;
    const text = part === "hour" ? hourLabel(draft.hour, is24Hour) : pad2(draft.minute);
    const label = t(part === "hour" ? "picker.hour" : "picker.minute");
    if (typing) {
      const invalid = part === "hour" ? typedHour == null : typedMinute == null;
      return (
        <View style={s.field}>
          <TextInput
            value={part === "hour" ? hourText : minuteText}
            onChangeText={part === "hour" ? setHourText : setMinuteText}
            onFocus={() => setFocused(part)}
            onBlur={() => setFocused((current) => (current === part ? null : current))}
            keyboardType="number-pad"
            maxLength={2}
            selectTextOnFocus
            autoFocus={part === "hour"}
            maxFontSizeMultiplier={DYNAMIC_TYPE_PICKER_MAX}
            style={[
              s.box,
              s.boxInput,
              { width: boxWidth, height: boxHeight },
              active && s.boxActive,
              active && s.boxInputFocused,
              invalid && s.boxInvalid,
            ]}
            accessibilityLabel={label}
            testID={`${testID}-${part}-input`}
          />
          <Text style={s.fieldCaption}>{label}</Text>
        </View>
      );
    }
    return (
      <Pressable
        onPress={() => {
          if (mode !== part) selection();
          setMode(part);
        }}
        style={[s.box, { width: boxWidth, height: boxHeight }, active && s.boxActive]}
        accessibilityRole="button"
        accessibilityLabel={`${label}, ${text}`}
        accessibilityState={{ selected: active }}
        testID={`${testID}-${part}`}
      >
        <Text
          style={[s.boxText, active && s.boxTextActive]}
          maxFontSizeMultiplier={DYNAMIC_TYPE_PICKER_MAX}
        >
          {text}
        </Text>
      </Pressable>
    );
  };

  return (
    <Dialog
      visible={visible}
      title={title ?? t(typing ? "picker.enter_time" : "picker.select_time")}
      titleVariant="label"
      width={TIME_PICKER_WIDTH}
      onClose={handleClose}
      avoidKeyboard={typing}
      testID={testID}
      footerStart={
        <IconButton
          name={typing ? "clock" : "keyboard"}
          size={IconSize.md}
          color={theme.textSecondary}
          onPress={typing ? stopTyping : startTyping}
          accessibilityLabel={t(typing ? "picker.use_clock" : "picker.use_keyboard")}
          testID={`${testID}-mode`}
        />
      }
      actions={[
        { label: t("common.cancel"), style: "cancel", testID: `${testID}-cancel` },
        {
          label: t("common.ok"),
          style: "primary",
          disabled: result == null,
          testID: `${testID}-ok`,
          onPress: () => {
            if (!result) return;
            confirmed.current = true;
            onConfirm(result);
          },
        },
      ]}
    >
      <View style={s.readout}>
        {readoutBox("hour")}
        <View style={[s.colonBox, { height: boxHeight }]}>
          <Text
            style={[s.colon, typing && s.colonTyping]}
            maxFontSizeMultiplier={DYNAMIC_TYPE_PICKER_MAX}
            accessibilityElementsHidden
            importantForAccessibility="no"
          >
            :
          </Text>
        </View>
        {readoutBox("minute")}
        {is24Hour ? null : (
          <View style={[s.period, { height: boxHeight }]} accessibilityRole="radiogroup">
            {([false, true] as const).map((isPm) => (
              <Pressable
                key={isPm ? "pm" : "am"}
                onPress={() => setPeriod(isPm)}
                style={[s.periodHalf, isPm && s.periodSplit, pm === isPm && s.periodActive]}
                accessibilityRole="radio"
                accessibilityState={{ checked: pm === isPm }}
                testID={`${testID}-${isPm ? "pm" : "am"}`}
              >
                <Text style={[s.periodText, pm === isPm && s.periodTextActive]}>
                  {isPm ? periods.pm : periods.am}
                </Text>
              </Pressable>
            ))}
          </View>
        )}
      </View>

      {typing ? (
        typedValid ? null : (
          <Text style={s.error} accessibilityLiveRegion="polite">
            {t("picker.invalid_time")}
          </Text>
        )
      ) : (
        <View style={s.dialWrap}>
          <ClockDial
            mode={mode}
            hour={draft.hour}
            minute={draft.minute}
            is24Hour={is24Hour}
            size={dialSize}
            accessibilityLabel={t(mode === "hour" ? "picker.hour" : "picker.minute")}
            accessibilityValueText={spokenTime}
            testID={`${testID}-dial`}
            onHourChange={(hour, final) => {
              setDraft((current) => ({ ...current, hour }));
              if (final) setMode("minute");
            }}
            onMinuteChange={(minute) => setDraft((current) => ({ ...current, minute }))}
          />
        </View>
      )}
    </Dialog>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    readout: {
      flexDirection: "row",
      alignItems: "flex-start",
      marginTop: Space.sm,
    },
    field: { alignItems: "flex-start", gap: Space.xxs },
    fieldCaption: { ...Type.caption, color: t.textSecondary },
    box: {
      borderRadius: Radius.xs,
      backgroundColor: t.control,
      alignItems: "center",
      justifyContent: "center",
    },
    boxActive: { backgroundColor: t.primaryLight },
    boxInput: {
      ...Type.clock,
      color: t.text,
      textAlign: "center",
      padding: 0,
      borderWidth: 2,
      borderColor: "transparent",
    },
    boxInputFocused: { borderColor: t.primary, color: t.primary },
    boxInvalid: { borderColor: t.danger },
    boxText: { ...Type.clock, color: t.text },
    boxTextActive: { color: t.primary },
    colonBox: {
      width: COLON_WIDTH,
      alignItems: "center",
      justifyContent: "center",
    },
    colon: { ...Type.clock, color: t.text },
    colonTyping: { color: t.textSecondary },
    period: {
      width: PERIOD_WIDTH,
      marginLeft: Space.sm,
      borderRadius: Radius.xs,
      borderWidth: 1,
      borderColor: t.border,
      overflow: "hidden",
    },
    periodHalf: { flex: 1, alignItems: "center", justifyContent: "center" },
    periodSplit: { borderTopWidth: 1, borderTopColor: t.border },
    periodActive: { backgroundColor: t.primaryLight },
    periodText: { ...Type.label, ...Weight.semibold, color: t.textSecondary },
    periodTextActive: { color: t.primary },
    dialWrap: { marginTop: Space.lg, alignItems: "center" },
    error: { ...Type.caption, color: t.danger, marginTop: Space.xs },
  });
}
