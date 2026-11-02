import { useLayoutEffect, useRef, type RefObject } from "react";

/**
 * A ref holding the latest `value`, for callbacks that outlive the render that made
 * them. It is written once the render commits, never during it: a render React throws
 * away must not leak its values (code-health audit CLAR-04, `react-hooks/refs`).
 */
export function useLatestRef<T>(value: T): RefObject<T> {
  const ref = useRef(value);
  useLayoutEffect(() => {
    ref.current = value;
  });
  return ref;
}
