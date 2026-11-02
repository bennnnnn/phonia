import {
  KEY_HEIGHT_MIN,
  PAD_GAP,
  PAD_PADDING_V,
  TAB_ROW_HEIGHT,
  mathPadHeight,
  padKeyHeight,
} from "@/lib/math/keyboardPad";
import { PAD_ROWS } from "@/lib/math/keyboardPages";

describe("math pad height", () => {
  it("never leaves a key under 44pt", () => {
    const pad = mathPadHeight(0);
    expect(padKeyHeight(pad)).toBe(KEY_HEIGHT_MIN);
    expect(PAD_PADDING_V + TAB_ROW_HEIGHT + PAD_ROWS * (KEY_HEIGHT_MIN + PAD_GAP)).toBe(pad);
  });

  it("matches a taller system keyboard by growing every key alike", () => {
    expect(mathPadHeight(480)).toBe(480);
    const key = padKeyHeight(480);
    expect(key).toBeGreaterThan(KEY_HEIGHT_MIN);
    expect(PAD_PADDING_V + TAB_ROW_HEIGHT + PAD_ROWS * (key + PAD_GAP)).toBeLessThanOrEqual(480);
  });

  it("ignores an accessory bar reported as a keyboard", () => {
    expect(mathPadHeight(120)).toBe(mathPadHeight(0));
  });
});
