/**
 * Soft offline-send feedback: keep the draft, avoid a blocking Alert (no
 * outbox/queue yet). Callers show a toast via `showToast`.
 */
export function notifyOfflineSendBlocked(options: {
  warn: () => void;
  showToast?: () => void;
}): void {
  options.warn();
  options.showToast?.();
}
