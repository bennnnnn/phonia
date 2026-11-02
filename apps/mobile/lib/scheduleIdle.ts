/** Defer work until the UI is idle (replaces deprecated InteractionManager.runAfterInteractions). */
export function scheduleIdleTask(callback: () => void): () => void {
  if (typeof requestIdleCallback === "function") {
    const handle = requestIdleCallback(() => {
      callback();
    });
    return () => cancelIdleCallback(handle);
  }
  const handle = setTimeout(callback, 1);
  return () => clearTimeout(handle);
}

/** Promise helper for one-shot deferral after UI settles (e.g. before opening a native picker). */
export function scheduleIdlePromise(): Promise<void> {
  return new Promise((resolve) => {
    scheduleIdleTask(() => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => resolve());
      });
    });
  });
}
