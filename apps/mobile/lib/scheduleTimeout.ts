export type TimeoutHandle = ReturnType<typeof setTimeout> | null;

export function clearScheduledTimeout(ref: { current: TimeoutHandle }): void {
  if (ref.current != null) {
    clearTimeout(ref.current);
    ref.current = null;
  }
}

export function scheduleTimeout(
  ref: { current: TimeoutHandle },
  delayMs: number,
  fn: () => void,
): void {
  clearScheduledTimeout(ref);
  ref.current = setTimeout(() => {
    ref.current = null;
    fn();
  }, delayMs);
}
