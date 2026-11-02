const emptyChatChecks = new Map<string, Promise<void>>();

/** One empty-check per chat — New chat + route-clear used to list twice. */
export function shareEmptyChatCheck(
  chatId: string,
  run: () => Promise<void>,
): Promise<void> {
  const existing = emptyChatChecks.get(chatId);
  if (existing) return existing;
  const task = run().finally(() => {
    if (emptyChatChecks.get(chatId) === task) emptyChatChecks.delete(chatId);
  });
  emptyChatChecks.set(chatId, task);
  return task;
}

/** Route-change effect already discards the previous routed chat. */
export function shouldDiscardOnNewChat(routeChatId: string | undefined): boolean {
  return routeChatId == null;
}

export function resolveActiveChatId(
  chatId: string | null,
  draftChatId: string | null,
): string | null {
  return chatId ?? draftChatId;
}

/** True when the thread already has a user or assistant turn (not an unused draft). */
export function chatHasThreadContent(
  messages: readonly { role: string }[],
): boolean {
  return messages.some((m) => m.role === "user" || m.role === "assistant");
}

/** Skip the empty-check GET when the thread already has a user or assistant turn. */
export function shouldProbeEmptyChat(hasThreadContent: boolean): boolean {
  return !hasThreadContent;
}

/** New chat clears messages before the route effect runs — remember replies. */
const knownAssistantChats = new Set<string>();

export function markChatHasAssistant(chatId: string): void {
  knownAssistantChats.add(chatId);
}

function chatHasKnownAssistant(chatId: string): boolean {
  return knownAssistantChats.has(chatId);
}

export function clearKnownAssistantChats(): void {
  knownAssistantChats.clear();
}

/** Probe only when we have never seen a user or assistant turn on this chat. */
export function shouldProbePreviousChat(opts: {
  chatId: string;
  messagesHadAssistant: boolean;
}): boolean {
  return shouldProbeEmptyChat(
    opts.messagesHadAssistant || chatHasKnownAssistant(opts.chatId),
  );
}

export function shouldWarmDraftSocket(options: {
  account: string | null;
  draftChatId: string | null;
  chatId: string | null;
  streaming: boolean;
}): boolean {
  return Boolean(
    options.account &&
      options.draftChatId &&
      !options.chatId &&
      !options.streaming,
  );
}
