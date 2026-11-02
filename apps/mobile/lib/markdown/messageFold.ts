/** Matches FEATURES.md ~320px collapse threshold (approx. 13 lines at 16/25). */
export const MESSAGE_FOLD_MAX_HEIGHT = 320;

export function shouldCollapseMessage(content: string): boolean {
  const trimmed = content.trim();
  if (!trimmed) return false;
  const lines = trimmed.split("\n").length;
  return trimmed.length > 520 || lines > 13;
}
