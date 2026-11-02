import type { Message, SearchSource } from "@/lib/api";
import { parseSearchSources, searchSourcesFromField, stripSearchSourcesFromContent } from "@/lib/searchSources";

/** The day's usage a `done` reports (code-health audit NET-14). */
export type TurnUsage = { used_tokens: number; daily_limit: number };

export type ChatWsPayload = {
  type: string;
  content?: string;
  message?: string;
  message_id?: string;
  code?: string;
  phase?: string;
  /** Optional activity context for a `status` event (e.g. the search query). */
  detail?: string;
  /** On a `status` event: how long its phase had run when it was sent (`thinking`). */
  elapsed_ms?: number;
  reasoning?: string;
  final_content?: string;
  /** The turn changed the to-do list. */
  todos_changed?: boolean;
  /** On `done`: the day's usage after the turn, for the quota nudge. */
  usage?: TurnUsage;
  search_sources?: SearchSource[];
  resolved_model?: string;
  completion?: string;
  /** On an `error`: whether the turn's user message is in the chat (Retry vs Regenerate). */
  user_message_saved?: boolean;
  /** Follow-up questions on a `related_prompts` event. The message field stays `related_prompts`. */
  prompts?: unknown;
};

const STOPPED_STREAM_DELTA_TYPES = new Set([
  "start",
  "token",
  "status",
  "reasoning",
  "stream_end",
]);

/** Late stream deltas after Stop must not mutate the committed partial bubble. */
export function shouldIgnoreStoppedStreamEvent(
  type: string,
  streaming: boolean,
): boolean {
  return !streaming && STOPPED_STREAM_DELTA_TYPES.has(type);
}

/**
 * `done` carries `search_sources` as JSON text and `todos_sync: "1"` today; ES-45 sends an
 * array and `todos_changed: true`. Either reads the same past this point. The day's usage
 * comes as the strings `used_tokens` and `daily_limit`, read into `usage`.
 */
function wholeNumber(value: unknown): number | null {
  if (typeof value !== "string" && typeof value !== "number") return null;
  const number = typeof value === "number" ? value : Number(value.trim() || Number.NaN);
  return Number.isSafeInteger(number) && number >= 0 ? number : null;
}

function turnUsageFrom(usedTokens: unknown, dailyLimit: unknown): TurnUsage | null {
  const used = wholeNumber(usedTokens);
  const limit = wholeNumber(dailyLimit);
  return used !== null && limit !== null && limit > 0 ? { used_tokens: used, daily_limit: limit } : null;
}

function normalizeChatWsPayload(wire: Record<string, unknown>): ChatWsPayload {
  const {
    search_sources: sources,
    todos_sync: todosSync,
    todos_changed: todosChanged,
    used_tokens: usedTokens,
    daily_limit: dailyLimit,
    ...rest
  } = wire;
  const payload = rest as ChatWsPayload;
  const searchSources = searchSourcesFromField(sources);
  if (searchSources.length > 0) payload.search_sources = searchSources;
  if (todosChanged === true || todosSync === "1") payload.todos_changed = true;
  const usage = turnUsageFrom(usedTokens, dailyLimit);
  if (usage) payload.usage = usage;
  return payload;
}

export function parseChatWsPayload(raw: string): ChatWsPayload | null {
  let wire: unknown;
  try {
    wire = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!wire || typeof wire !== "object" || Array.isArray(wire)) return null;
  return normalizeChatWsPayload(wire as Record<string, unknown>);
}

function relatedPromptsFrom(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const prompts = value.filter(
    (item): item is string => typeof item === "string" && item.trim().length > 0,
  );
  return prompts.length > 0 ? prompts.slice(0, 3) : undefined;
}

/** The wire event is `{ type, message_id, prompts }`, not the message field name. */
export function relatedPromptsFromEvent(payload: ChatWsPayload): string[] | undefined {
  return relatedPromptsFrom(payload.prompts);
}

type DoneMergeInput = {
  finalId: string;
  messageId?: string;
  draftContent: string;
  finalContent?: string;
  search_sources?: SearchSource[];
  draftSearchSources?: SearchSource[];
  model?: string | null;
  /**
   * Local id given to the streaming bubble when the user stopped generation
   * (e.g. `streamed-<ts>`). When the server's `done` arrives after a stop,
   * we reconcile that bubble in place (picking up the authoritative
   * `final_content` + real `message_id`) instead of appending a duplicate.
   * If non-null and the id is no longer present, the `done` is dropped.
   */
  stoppedStreamedId?: string | null;
  generationStopped?: boolean;
  /**
   * The server saved the reply as the user stopped it (`completion: user_stop`):
   * `final_content` is the text this phone drew, made safe, never longer.
   */
  savedAsStopped?: boolean;
};

/** Pure merge for the WebSocket `done` event — used by useChat and unit tests. */
export function mergeDoneIntoMessages(
  prev: Message[],
  input: DoneMergeInput,
): Message[] {
  const {
    finalId,
    messageId,
    draftContent,
    finalContent,
    search_sources,
    draftSearchSources,
    model,
    stoppedStreamedId,
    generationStopped,
    savedAsStopped,
  } = input;

  // The saved reply is on screen already (a read brought it first): its stand-in goes, so it never shows twice.
  if (messageId && prev.some((m) => m.id === messageId)) {
    const rest = prev.filter((m) => m.id !== "streaming" && m.id !== stoppedStreamedId);
    return rest.length === prev.length ? prev : rest;
  }

  if (prev.some((m) => m.id === "streaming")) {
    if (!messageId && !draftContent.trim()) {
      return prev.filter((m) => m.id !== "streaming");
    }
    return prev.map((m) =>
      m.id === "streaming"
        ? {
            ...m,
            id: finalId,
            renderKey: m.renderKey,
            content: stripSearchSourcesFromContent(
              finalContent ?? (draftContent || m.content),
            ),
            search_sources:
              search_sources ??
              draftSearchSources ??
              parseSearchSources(finalContent ?? draftContent ?? m.content),
            model: model ?? m.model,
            generationStopped: m.generationStopped || generationStopped,
          }
        : m,
    );
  }

  // User stopped generation: the streaming bubble was already committed
  // locally as `stoppedStreamedId`. Reconcile it in place (the real id)
  // instead of appending. A stopped answer never changes past what the user
  // saw: it takes the server's text only when the server saved it as stopped
  // (the text this phone drew, made safe); a reply the server finished anyway,
  // with cards or a tail the user never saw, keeps the bubble's own text.
  if (stoppedStreamedId) {
    const stopped = prev.find((m) => m.id === stoppedStreamedId);
    if (!stopped) {
      // Bubble is gone (chat switched / new send) — drop the late done.
      return prev;
    }
    const kept = savedAsStopped ? (finalContent ?? stopped.content) : stopped.content;
    const content = stripSearchSourcesFromContent(kept);
    if (!messageId && !content.trim()) {
      return prev.filter((m) => m.id !== stoppedStreamedId);
    }
    return prev.map((m) =>
      m.id === stoppedStreamedId
        ? {
            ...m,
            id: finalId,
            content,
            search_sources: m.search_sources ?? parseSearchSources(kept),
            model: model ?? m.model,
            generationStopped: m.generationStopped || generationStopped,
          }
        : m,
    );
  }

  const next = [...prev];
  const content = stripSearchSourcesFromContent(finalContent ?? draftContent);
  if (!content.trim()) {
    return next;
  }
  return [
    ...next,
    {
      id: finalId,
      role: "assistant" as const,
      content,
      model: model ?? null,
      search_sources: search_sources ?? parseSearchSources(content),
      created_at: new Date().toISOString(),
      generationStopped,
    },
  ];
}

/** Attach follow-up questions from the event that arrives after `done`. */
export function applyRelatedPrompts(
  messages: Message[],
  messageId: string,
  prompts: string[],
): Message[] {
  if (!messageId || prompts.length === 0) return messages;
  let changed = false;
  const next = messages.map((message) => {
    if (message.id !== messageId) return message;
    changed = true;
    return { ...message, related_prompts: prompts };
  });
  return changed ? next : messages;
}

/** Apply resolved model to the in-flight streaming bubble as soon as stream_end arrives. */
export function applyStreamEndModel(
  messages: Message[],
  model: string | undefined,
): Message[] {
  if (!model) return messages;
  return messages.map((m) =>
    m.id === "streaming" ? { ...m, model } : m,
  );
}

export function buildDoneMergeInput(
  payload: ChatWsPayload,
  draft: { content: string; search_sources?: SearchSource[] } | null,
  now = Date.now(),
  stoppedStreamedId: string | null = null,
): DoneMergeInput {
  const finalContent =
    typeof payload.final_content === "string" ? payload.final_content : undefined;
  const completion = payload.completion;
  return {
    finalId: payload.message_id ?? `streamed-${now}`,
    messageId: payload.message_id,
    draftContent: draft?.content ?? "",
    finalContent,
    search_sources: payload.search_sources,
    draftSearchSources: draft?.search_sources,
    model: payload.resolved_model ?? null,
    stoppedStreamedId,
    generationStopped: completion === "interrupted" || completion === "user_stop",
    savedAsStopped: completion === "user_stop",
  };
}
