import type { CustomIconName } from "./custom";
import type { LucideIconName } from "./glyphs.generated";

/** Every icon the app can draw: Lucide line icons plus the few app-only glyphs. */
export type IconName = LucideIconName | CustomIconName;
