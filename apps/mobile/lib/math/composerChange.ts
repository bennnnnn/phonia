import type { TextSelection } from "@/lib/math/keyboardSymbols";

/** Native replace range: prev[at:at+removed] → added. */
export function nativeEditRange(
  prev: string,
  next: string,
): { at: number; removed: string; added: string } | null {
  if (prev === next) return null;
  let i = 0;
  const minLen = Math.min(prev.length, next.length);
  while (i < minLen && prev[i] === next[i]) i += 1;
  let pe = prev.length;
  let ne = next.length;
  while (pe > i && ne > i && prev[pe - 1] === next[ne - 1]) {
    pe -= 1;
    ne -= 1;
  }
  return { at: i, removed: prev.slice(i, pe), added: next.slice(i, ne) };
}

/**
 * Parked TextInputs keep the OS caret in a LaTeX slot while the preview
 * caret is elsewhere. Replay the same insert/delete at `pin`.
 */
export function applyPinnedTextChange(
  prev: string,
  next: string,
  pin: TextSelection,
): { text: string; caret: number } {
  const range = nativeEditRange(prev, next);
  if (!range) return { text: next, caret: pin.start };
  const pinStart = Math.max(0, Math.min(pin.start, prev.length));
  const pinEnd = Math.max(pinStart, Math.min(pin.end, prev.length));
  const { at, removed, added } = range;
  const collapsed = pinStart === pinEnd;

  if (collapsed) {
    const insertAtPin = added.length > 0 && removed.length === 0 && at === pinStart;
    const backspaceAtPin =
      added.length === 0 && removed.length > 0 && at + removed.length === pinStart;
    const deleteAtPin = added.length === 0 && removed.length > 0 && at === pinStart;
    if (insertAtPin || backspaceAtPin || deleteAtPin) {
      return { text: next, caret: at + added.length };
    }
    if (added.length > 0 && removed.length === 0) {
      const text = prev.slice(0, pinStart) + added + prev.slice(pinEnd);
      return { text, caret: pinStart + added.length };
    }
    if (added.length === 0 && removed.length > 0) {
      const from = Math.max(0, pinStart - removed.length);
      const text = prev.slice(0, from) + prev.slice(pinStart);
      return { text, caret: from };
    }
  } else if (at === pinStart && at + removed.length === pinEnd) {
    return { text: next, caret: at + added.length };
  }

  const text = prev.slice(0, pinStart) + added + prev.slice(pinEnd);
  return { text, caret: pinStart + added.length };
}

/** After closing the math bar, sit after the last `$...$` (or at end). */
export function caretAfterMathBarClose(text: string): number {
  const lastDollar = text.lastIndexOf("$");
  if (lastDollar === -1) return text.length;
  return lastDollar + 1;
}
