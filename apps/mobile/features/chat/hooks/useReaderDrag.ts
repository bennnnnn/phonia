import { useCallback, useEffect, useRef, type MutableRefObject } from "react";
import type { NativeScrollEvent, NativeSyntheticEvent } from "react-native";

import { clearScheduledTimeout, scheduleTimeout, type TimeoutHandle } from "@/lib/scheduleTimeout";

/** Let go faster than this (points per ms), a drag is a flick: momentum follows. */
const FLICK_VELOCITY = 0.01;
/** A flick's momentum starts within a frame or two; past this none is coming. */
export const MOMENTUM_WAIT_MS = 120;

type ScrollEvent = NativeSyntheticEvent<NativeScrollEvent>;

/**
 * Whether the reader is moving the list: from the drag's start to the end of
 * its scroll. A drag that ends with speed is a flick whose momentum begins a
 * moment later; the reader is still moving the list in between, so it stays
 * moving until the momentum ends, or until none came. `settle` reads where
 * the list is (from the event, when there is one).
 */
export function useReaderDrag(settle: (event?: ScrollEvent) => void): {
  movingRef: MutableRefObject<boolean>;
  begin: () => void;
  endDrag: (event: ScrollEvent) => void;
  end: () => void;
} {
  const movingRef = useRef(false);
  const momentumWaitRef = useRef<TimeoutHandle>(null);

  const begin = useCallback(() => {
    movingRef.current = true;
    clearScheduledTimeout(momentumWaitRef);
  }, []);

  const end = useCallback(() => {
    clearScheduledTimeout(momentumWaitRef);
    movingRef.current = false;
    settle();
  }, [settle]);

  const endDrag = useCallback(
    (event: ScrollEvent) => {
      if (Math.abs(event.nativeEvent.velocity?.y ?? 0) <= FLICK_VELOCITY) {
        end();
        return;
      }
      settle(event);
      scheduleTimeout(momentumWaitRef, MOMENTUM_WAIT_MS, end);
    },
    [end, settle],
  );

  useEffect(() => () => clearScheduledTimeout(momentumWaitRef), []);

  return { movingRef, begin, endDrag, end };
}
