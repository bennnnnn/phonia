/** Shared profile display + edit helpers for Settings and Avatar. */

export function sanitizeDisplayName(raw: string): string | null {
  const name = raw.trim().replace(/\s+/g, " ");
  if (!name || name.length > 80) return null;
  return name;
}

export function getDisplayName(
  name: string | null | undefined,
  fallback: string,
): string {
  const trimmed = name?.trim();
  return trimmed || fallback;
}

export function getInitials(name: string | null | undefined): string {
  if (!name?.trim()) return "?";
  const letters = name
    .trim()
    .split(/\s+/)
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return letters || "?";
}
