import { fireEvent, render, within } from "@testing-library/react-native";
import { Dimensions, StyleSheet, type TextStyle, type ViewStyle } from "react-native";

import { DYNAMIC_TYPE_PICKER_MAX } from "@/lib/type";
import { UI_LINE_EM } from "@/lib/uiFont";

import { DatePickerDialog } from "../DatePickerDialog";
import { TimePickerDialog } from "../TimePickerDialog";

const hidden = { includeHiddenElements: true };

/** iOS text sizes as React Native scales them: default, xLarge, xxLarge, xxxLarge, AX1, AX5. */
const SCALES = [1, 1.118, 1.235, 1.353, 1.786, 3.571];
/** A Source Sans 3 digit's advance, in em (tabular; 0.513 in semibold). */
const DIGIT_EM = { regular: 0.497, semibold: 0.513 };

type Node = {
  props: Record<string, unknown>;
  parent: Node | null;
};

function style(node: Node): TextStyle & ViewStyle {
  return StyleSheet.flatten(node.props.style as TextStyle) ?? {};
}

/** The text's size at `fontScale`: it grows with the reader's setting until its own cap. */
function drawnSize(text: Node, fontScale: number): number {
  const cap = (text.props.maxFontSizeMultiplier as number | undefined) ?? Infinity;
  return Number(style(text).fontSize) * Math.min(fontScale, cap);
}

/** The nearest box around `node` (itself included) that sets a height. */
function boxAround(node: Node): { width?: number; height: number } {
  for (let at: Node | null = node; at; at = at.parent) {
    const { width, height } = style(at);
    if (typeof height === "number") return { width: typeof width === "number" ? width : undefined, height };
  }
  throw new Error("no sized box");
}

function atFontScale(fontScale: number, width = 375) {
  jest.spyOn(Dimensions, "get").mockReturnValue({ width, height: 812, scale: 3, fontScale });
}

afterEach(() => jest.restoreAllMocks());

describe("time picker at large text sizes", () => {
  async function openTime() {
    return render(
      <TimePickerDialog
        visible
        value={{ hour: 21, minute: 11 }}
        is24Hour={false}
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );
  }

  it.each(SCALES)("fits the capped readout in its boxes at %s×", async (fontScale) => {
    atFontScale(fontScale);
    const view = await openTime();
    const hourBox = view.getByTestId("time-picker-hour", hidden);
    const hour = within(hourBox).getByText("9", hidden);
    const minute = within(view.getByTestId("time-picker-minute", hidden)).getByText("11", hidden);
    const colon = view.getByText(":", hidden);
    for (const digits of [hour, minute, colon]) {
      expect(digits.props.maxFontSizeMultiplier).toBe(DYNAMIC_TYPE_PICKER_MAX);
    }
    const size = drawnSize(hour, fontScale);
    const box = boxAround(hourBox);
    expect(size * UI_LINE_EM).toBeLessThanOrEqual(box.height);
    expect(2 * DIGIT_EM.regular * size).toBeLessThanOrEqual(box.width ?? 0);
    // The colon and AM/PM stand as tall as the boxes, so the row stays level.
    expect(boxAround(colon).height).toBe(box.height);
    expect(boxAround(view.getByTestId("time-picker-am", hidden)).height).toBe(box.height);
    if (fontScale === 1) expect(box.height).toBe(80);

    await fireEvent.press(view.getByTestId("time-picker-mode", hidden));
    const input = view.getByTestId("time-picker-hour-input", hidden);
    expect(input.props.maxFontSizeMultiplier).toBe(DYNAMIC_TYPE_PICKER_MAX);
    expect(boxAround(input).height).toBe(box.height);
  });

  it.each(SCALES)("keeps the dial's numbers inside its 48pt handle at %s×", async (fontScale) => {
    atFontScale(fontScale);
    const view = await openTime();
    const labels = within(view.getByTestId("time-picker-dial", hidden)).getAllByText(/^\d+$/, hidden);
    expect(labels.length).toBeGreaterThan(0);
    for (const label of labels) {
      expect(label.props.maxFontSizeMultiplier).toBe(DYNAMIC_TYPE_PICKER_MAX);
      const size = drawnSize(label, fontScale);
      const box = boxAround(label);
      expect(size * UI_LINE_EM).toBeLessThanOrEqual(box.height);
      expect(2 * DIGIT_EM.regular * size).toBeLessThanOrEqual(box.width ?? 0);
    }
  });
});

describe("date picker at large text sizes", () => {
  async function openDate() {
    return render(
      <DatePickerDialog
        visible
        value={new Date(2026, 8, 26, 8, 30)}
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );
  }

  // 375 is the narrowest iPhone; 320 the narrowest phone the grid shrinks for (32pt cells).
  it.each(SCALES.flatMap((fontScale) => [[fontScale, 375], [fontScale, 320]]))(
    "fits days and years in their cells at %s× on a %spt screen",
    async (fontScale, width) => {
      atFontScale(fontScale, width);
      const view = await openDate();
      for (const day of [3, 26]) {
        const cell = view.getByTestId(`date-picker-day-${day}`, hidden);
        const digits = within(cell).getByText(String(day), hidden);
        expect(digits.props.maxFontSizeMultiplier).toBe(DYNAMIC_TYPE_PICKER_MAX);
        const size = drawnSize(digits, fontScale);
        const box = boxAround(cell);
        expect(size * UI_LINE_EM).toBeLessThanOrEqual(box.height);
        expect(2 * DIGIT_EM.semibold * size).toBeLessThanOrEqual(box.width ?? 0);
      }

      await fireEvent.press(view.getByTestId("date-picker-years-toggle", hidden));
      const chip = view.getByTestId("date-picker-year-2026", hidden);
      const year = within(chip).getByText("2026", hidden);
      expect(year.props.maxFontSizeMultiplier).toBe(DYNAMIC_TYPE_PICKER_MAX);
      const size = drawnSize(year, fontScale);
      const box = boxAround(chip);
      expect(size * UI_LINE_EM).toBeLessThanOrEqual(box.height);
      expect(4 * DIGIT_EM.semibold * size).toBeLessThanOrEqual(box.width ?? 0);
    },
  );
});
