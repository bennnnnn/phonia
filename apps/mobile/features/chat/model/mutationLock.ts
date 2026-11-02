// Header, drawer menu and bulk actions can all target the same conversation.
// Keep optimistic updates exclusive until their server result is reconciled.
const pendingMutations = new Set<string>();

export function beginChatMutation(
  session: number,
  chatIds: readonly string[],
): (() => void) | null {
  const keys = [...new Set(chatIds)].map((id) => `${session}:${id}`);
  if (keys.some((key) => pendingMutations.has(key))) return null;
  keys.forEach((key) => pendingMutations.add(key));
  return () => keys.forEach((key) => pendingMutations.delete(key));
}
