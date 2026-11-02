import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";

/**
 * Async work belongs to the view that started it. A view ends when `key` changes
 * (another chat, account or drawer state) or the hook unmounts; work that finishes
 * after its view ended does nothing. The current view moves when a render commits,
 * never during render (code-health audit CLAR-04).
 */
export function useViewOwner(key: string) {
  const view = useMemo(() => ({ key }), [key]);
  const state = useRef({ view, mounted: true });
  useLayoutEffect(() => {
    state.current.view = view;
  }, [view]);
  useEffect(() => {
    const current = state.current;
    current.mounted = true;
    return () => {
      current.mounted = false;
    };
  }, []);
  /** The view on screen now, for work that starts later and checks it at the end. */
  const currentView = useCallback(() => state.current.view, []);
  /** The hook is still mounted, whichever view it shows. */
  const mounted = useCallback(() => state.current.mounted, []);
  /** True while `owner` (by default this render's view) is the mounted view on screen. */
  const owns = useCallback(
    (owner: object = view) => state.current.mounted && state.current.view === owner,
    [view],
  );
  return { view, currentView, owns, mounted };
}
