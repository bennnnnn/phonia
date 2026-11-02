import type { Message } from "@/lib/api";

/** Remove the last assistant turn for regenerate; keep a copy to restore on failure. */
export function popLastAssistantMessage(messages: Message[]): {
  backup: Message | null;
  messages: Message[];
} {
  const next = [...messages];
  const last = next[next.length - 1];
  if (last?.role !== "assistant") {
    return { backup: null, messages: next };
  }
  next.pop();
  return { backup: last, messages: next };
}

/**
 * The thread without the replacement's streaming row, and with the prior reply
 * back in that row's place when regenerate fails before a replacement, so a
 * message sent meanwhile stays below it. With no streaming row it goes last.
 */
export function restoreAssistantMessage(
  messages: Message[],
  backup: Message | null,
): Message[] {
  const at = messages.findIndex((m) => m.id === "streaming");
  const rest = at < 0 ? messages : messages.filter((m) => m.id !== "streaming");
  if (!backup || rest.some((m) => m.id === backup.id)) return rest;
  const place = at < 0 ? rest.length : at;
  return [...rest.slice(0, place), backup, ...rest.slice(place)];
}
