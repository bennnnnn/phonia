/**
 * The house pattern for module-level stores (`streamingDraftStore`,
 * `appearanceRuntime`, the composer queues, ...): a set of listeners where
 * `subscribe` hands back its own unsubscribe and `emit` calls every listener
 * in subscription order. A listener added during an emit is called in that
 * same emit; one removed before its turn is not (`Set` iteration).
 */
type ListenerSet<Args extends unknown[] = []> = {
  subscribe: (listener: (...args: Args) => void) => () => void;
  emit: (...args: Args) => void;
  /** Test helpers reset module state between cases. */
  clear: () => void;
};

export function createListenerSet<Args extends unknown[] = []>(): ListenerSet<Args> {
  const listeners = new Set<(...args: Args) => void>();
  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    emit(...args) {
      listeners.forEach((listener) => listener(...args));
    },
    clear() {
      listeners.clear();
    },
  };
}

/**
 * One value plus its listeners, read with `useSyncExternalStore(subscribe, get)`.
 * `set` notifies only when the value changes (`===`).
 */
type ValueStore<T> = {
  get: () => T;
  set: (next: T) => void;
  subscribe: (listener: () => void) => () => void;
  /** Back to the initial value with no listeners (tests). */
  reset: () => void;
};

export function createValueStore<T>(initial: T): ValueStore<T> {
  let value = initial;
  const listeners = createListenerSet();
  return {
    get: () => value,
    set(next) {
      if (value === next) return;
      value = next;
      listeners.emit();
    },
    subscribe: listeners.subscribe,
    reset() {
      value = initial;
      listeners.clear();
    },
  };
}
