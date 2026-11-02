import { useEffect } from "react";

import type { FenceId } from "@/lib/fenceRegistry";
import { refusalOf, type FenceRefusal } from "@/lib/fenceReports";
import { reportFenceRefused } from "@/lib/sentry";

type RefusalShape = Parameters<typeof refusalOf>[1];

/**
 * A block that would not draw its fence says so once, when it mounts or its body
 * changes: the fence's id and a reason code (`reason`, or read from the body's shape),
 * never the body. Sentry rate-limits it (`reportFenceRefused`), so a long chat of
 * broken fences sends a handful at most. `shape` is a module constant, not an object
 * built in render.
 */
export function useFenceRefused(
  fence: FenceId,
  content: string,
  refused: boolean,
  shape?: RefusalShape,
  reason?: FenceRefusal,
): void {
  useEffect(() => {
    if (refused) reportFenceRefused(fence, reason ?? refusalOf(content, shape));
  }, [fence, content, refused, shape, reason]);
}
