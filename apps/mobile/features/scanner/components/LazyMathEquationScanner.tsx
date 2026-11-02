/**
 * The scanner (camera, live text detection, crop and read-back review) loads
 * the first time it is opened, not with the chat screen, and only then asks
 * for the camera permission state. Once open it stays mounted, as the eager
 * scanner always was, so closing still plays its own dismissal.
 */
import type { ComponentProps } from "react";

import type { MathEquationScanner } from "@/features/scanner/components/MathEquationScanner";
import { lazyOverlay } from "@/ui/overlay/lazyOverlay";

export const LazyMathEquationScanner = lazyOverlay<ComponentProps<typeof MathEquationScanner>>(() =>
  import("@/features/scanner/components/MathEquationScanner").then((m) => ({ default: m.MathEquationScanner })),
);
