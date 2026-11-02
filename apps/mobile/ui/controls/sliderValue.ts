/**
 * The arithmetic behind `Slider`: where a value sits on the track, and which value a finger
 * position or an accessibility step lands on. Values snap to the step grid that starts at
 * `min`, and are printed back to the step's own decimals so 0.1 + 0.2 never shows as
 * 0.30000000000000004.
 */

function decimals(value: number): number {
  const text = String(value);
  const exponent = /e-(\d+)$/.exec(text);
  if (exponent) return Number(exponent[1]);
  return (text.split(".")[1] ?? "").length;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Where `value` sits on the track, from 0 at `min` to 1 at `max`. */
export function sliderFraction(value: number, min: number, max: number): number {
  if (!(max > min)) return 0;
  return clamp((value - min) / (max - min), 0, 1);
}

/** The value on the step grid nearest `raw`, inside `min`…`max`. */
export function snapSliderValue(raw: number, min: number, max: number, step: number): number {
  if (!(max > min)) return min;
  const bounded = clamp(raw, min, max);
  if (!(step > 0)) return bounded;
  const places = Math.min(12, Math.max(decimals(step), decimals(min)));
  const snapped = min + Math.round((bounded - min) / step) * step;
  return clamp(Number(snapped.toFixed(places)), min, max);
}

/** The value at a fraction of the track (a finger position), snapped. */
export function sliderValueAt(
  fraction: number,
  min: number,
  max: number,
  step: number,
): number {
  return snapSliderValue(min + clamp(fraction, 0, 1) * (max - min), min, max, step);
}

/** One step up or down from `value` (the screen reader's swipe), snapped. */
export function steppedSliderValue(
  value: number,
  direction: 1 | -1,
  min: number,
  max: number,
  step: number,
): number {
  return snapSliderValue(value + direction * step, min, max, step);
}
