import { hasSettingsProposalFence } from "@/lib/settingsProposal";

// Note: no estimatedItemSize / size hints here — FlashList v2 measures items
// itself and `overrideItemLayout` only supports span. Recycling quality comes
// from `getItemType` (messageListItemType below).

/**
 * Short threads stay under the header. FlashList's bottom start pads the top
 * until the rows fill the screen, so a few messages sit on the composer and
 * cannot scroll up. Only a thread that already has older pages is long enough
 * to open on the latest message. A single page that overflows is scrolled
 * after layout, not pinned with that pad.
 */
export function shouldStartRenderingFromBottom(options: {
  messageCount: number;
  hasMoreOlder: boolean;
}): boolean {
  return options.hasMoreOlder && options.messageCount > 0;
}

/** Keep the mount-time pin; never promote a short in-progress thread. */
export function latchStartRenderingFromBottom(options: {
  chatKey: string;
  previousChatKey: string;
  previousValue: boolean;
  messageCount: number;
  hasMoreOlder: boolean;
}): { chatKey: string; value: boolean } {
  if (options.chatKey !== options.previousChatKey) {
    return {
      chatKey: options.chatKey,
      value: shouldStartRenderingFromBottom({
        messageCount: options.messageCount,
        hasMoreOlder: options.hasMoreOlder,
      }),
    };
  }
  if (options.hasMoreOlder) {
    return { chatKey: options.chatKey, value: true };
  }
  return { chatKey: options.chatKey, value: options.previousValue };
}

/** Render keys assigned to the in-flight streaming placeholder (`stream-<ts>`). */
export function isFreshStreamRenderKey(renderKey?: string): boolean {
  return Boolean(renderKey?.startsWith("stream-"));
}

export function messageListItemType(item: {
  id: string;
  role: string;
  content?: string;
}): string {
  if (item.role !== "assistant") return item.role;
  const content = item.content ?? "";
  // Cheap gate: proposal cards always carry a fenced block, and most messages
  // have none — skip the full-content regex scans for them.
  if (!content.includes("```")) return "assistant";
  if (hasSettingsProposalFence(content)) return "assistant-settings";
  return "assistant";
}

export function messageListKey(item: { id: string; renderKey?: string }): string {
  return item.renderKey ?? item.id;
}
