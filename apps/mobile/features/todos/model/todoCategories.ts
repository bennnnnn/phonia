import { DEFAULT_TOPIC } from "@/features/todos/model/todoTopics";

/** Stable topic ids. Custom names are stored as the user typed them. */
export const BUILTIN_CATEGORIES = ["work", "personal", "wishlist", "birthday"] as const;

type BuiltinCategory = (typeof BUILTIN_CATEGORIES)[number];

const BUILTIN_SET = new Set<string>(BUILTIN_CATEGORIES);

export function isBuiltinCategory(topic: string): topic is BuiltinCategory {
  return BUILTIN_SET.has(topic);
}

/** Blank and the legacy default both mean no category. */
export function isNoCategory(topic: string | null | undefined): boolean {
  const name = topic?.trim();
  return !name || name === DEFAULT_TOPIC;
}

/**
 * Turn a typed category into a stored topic.
 * Built-in names collapse to their id so the label can be translated.
 */
export function resolveCategoryName(raw: string): string | null {
  const name = raw.trim().replace(/\s+/g, " ");
  if (!name || name.length > 200) return null;
  const key = name.toLowerCase();
  if (key === DEFAULT_TOPIC.toLowerCase() || key === "no category") return DEFAULT_TOPIC;
  if (isBuiltinCategory(key)) return key;
  return name;
}

export function categoryText(
  topic: string | null | undefined,
  t: (key: string) => string,
): string | null {
  const name = topic?.trim() ?? "";
  if (isNoCategory(name)) return null;
  if (isBuiltinCategory(name)) return t(`todos.category_${name}`);
  return name;
}
