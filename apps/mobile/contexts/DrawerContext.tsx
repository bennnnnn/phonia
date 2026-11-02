import { createContext, useContext, type ReactNode } from "react";

type DrawerControls = {
  open: () => void;
  close: () => void;
  /** Whether the drawer is open right now. For handlers and effects: reading it does not re-render. */
  isOpenNow: () => boolean;
};

/**
 * Two contexts so the chat screen under the drawer never re-renders when it
 * opens or closes: the controls never change, and only the pieces that draw
 * differently while it is open (the composer, the header, the drawer's list)
 * read the open state.
 */
const DrawerControlsContext = createContext<DrawerControls | null>(null);
const DrawerOpenContext = createContext(false);

export function DrawerProvider({
  controls,
  isOpen,
  children,
}: {
  /** Must keep its identity: every reader of the controls renders again when it changes. */
  controls: DrawerControls;
  isOpen: boolean;
  children: ReactNode;
}) {
  return (
    <DrawerControlsContext.Provider value={controls}>
      <DrawerOpenContext.Provider value={isOpen}>{children}</DrawerOpenContext.Provider>
    </DrawerControlsContext.Provider>
  );
}

/** Open, close, and the open state for event handlers, without subscribing to it. */
export function useDrawerControls(): DrawerControls {
  const controls = useContext(DrawerControlsContext);
  if (!controls) throw new Error("useDrawerControls must be used inside the drawer layout");
  return controls;
}

/** True while the drawer is open; the caller renders again when it opens or closes. False outside a drawer. */
export function useDrawerOpen(): boolean {
  return useContext(DrawerOpenContext);
}

/** Renders `children` only while the drawer is closed; nothing above it renders when that changes. */
export function WhileDrawerClosed({ children }: { children: ReactNode }) {
  return useDrawerOpen() ? null : children;
}
