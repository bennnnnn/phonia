/**
 * A full-screen overlay whose code loads the first time it opens, not with the
 * screen that holds it (lib/__tests__/launchImports.test.ts keeps it out of
 * launch). Once open it stays mounted, as an eager overlay always was, so
 * closing still plays its own dismissal (see FullScreenModal).
 *
 * `load` is a literal `import()` at the call site, so Metro defers the module.
 */
import { lazy, Suspense, useState, type ReactNode } from "react";

export function lazyOverlay<Props extends { visible: boolean }>(
  load: () => Promise<{ default: (props: Props) => ReactNode }>,
): (props: Props) => ReactNode {
  const Overlay = lazy(load);
  return function LazyOverlay(props: Props) {
    const [opened, setOpened] = useState(props.visible);
    if (props.visible && !opened) setOpened(true);
    if (!opened) return null;
    return (
      <Suspense fallback={null}>
        <Overlay {...props} />
      </Suspense>
    );
  };
}
