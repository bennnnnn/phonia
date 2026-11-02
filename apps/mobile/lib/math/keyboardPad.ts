import { Space } from "@/lib/space";
import { PAD_ROWS } from "@/lib/math/keyboardPages";

/** Vertical padding inside the gray pad (8 top + 12 bottom). */
export const PAD_PADDING_V = 20;
export const PAD_GAP = 6;
export const KEY_HEIGHT_MIN = Space.minTouch;
/** The page tabs above the keys. */
export const TAB_ROW_HEIGHT = Space.minTouch;
/** Below this, a reported keyboard height is an accessory bar, not a keyboard. */
const SYSTEM_KEYBOARD_MIN = 200;

/** Everything in the pad that is not a key: padding, tabs, and the gap above each row. */
const PAD_CHROME = PAD_PADDING_V + TAB_ROW_HEIGHT + PAD_ROWS * PAD_GAP;

/**
 * Gray pad height. It matches the phone's own keyboard when that height is
 * known, so ABC and the math pad swap without a jump, and it never leaves a key
 * under 44pt. Every page has six rows, so every page gets the same key height.
 */
export function mathPadHeight(systemKeyboard: number): number {
  const keyboard = systemKeyboard >= SYSTEM_KEYBOARD_MIN ? systemKeyboard : 0;
  return Math.max(keyboard, PAD_CHROME + PAD_ROWS * KEY_HEIGHT_MIN);
}

/** One key height for every page: the pad split evenly among its six rows. */
export function padKeyHeight(padHeight: number): number {
  return Math.max(KEY_HEIGHT_MIN, Math.floor((padHeight - PAD_CHROME) / PAD_ROWS));
}
