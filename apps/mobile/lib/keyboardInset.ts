/**
 * Keyboard geometry for the chat screen. `keyboardLiftAbove` runs inside a
 * Reanimated worklet, so it carries the 'worklet' directive and reads nothing
 * but its arguments; the other two run on the JS thread, on every keyboard
 * frame the UI thread forwards there.
 */

/**
 * The height to hand to React state, or null while the keyboard is still
 * moving. React only needs where the keyboard comes to rest: the composer,
 * the list's bottom space and the chrome above the composer follow every
 * frame on the UI thread. `state` is Reanimated's `KeyboardState`, which
 * reports OPEN and CLOSED once the native show or hide has finished.
 */
export function settledKeyboardHeight(state: number, height: number): number | null {
  // KeyboardState.OPEN and KeyboardState.CLOSED.
  const open = 2;
  const closed = 4;
  if (state === open) return Math.max(0, height);
  if (state === closed) return 0;
  return null;
}

/**
 * Whether a keyboard frame is a step the thread should follow: the first
 * frame of a show or a hide, every `thresholdPx` of travel, and the frame the
 * keyboard comes to rest on.
 *
 * `lastPushed` is the last height that was a step — not the previous animation
 * frame. Comparing frames at a 48px gate never catches the rest of a smooth
 * iOS curve (~16px/frame), so the thread stopped short of the keyboard.
 */
export function shouldPushKeyboardHeight(
  next: number,
  lastPushed: number,
  thresholdPx: number,
  previousFrame: number = lastPushed,
): boolean {
  const isOpenTransition = (next > 0) !== (lastPushed > 0);
  if (isOpenTransition) return true;
  if (Math.abs(next - lastPushed) >= thresholdPx) return true;
  // Last step of the curve is often under the threshold — still commit rest.
  return next === previousFrame && next !== lastPushed;
}

/**
 * How far the keyboard has raised the composer above its resting place. At
 * rest the composer sits on `idleBottomPad` (the home indicator); with the
 * keyboard up it sits on the keyboard instead, so the rise is the difference.
 */
export function keyboardLiftAbove(keyboardHeight: number, idleBottomPad: number): number {
  "worklet";
  return keyboardHeight > idleBottomPad ? keyboardHeight - idleBottomPad : 0;
}
