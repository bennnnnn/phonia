import { speechApi } from "@/features/speech/api";
import type { SearchSource } from "@/lib/api/types";

export type RealtimeFunctionCall = { type: "function_call"; name: string; call_id: string; arguments: string };
export type RealtimeToolResult = { content: string; sources?: SearchSource[] };

export function realtimeFunctionCalls(response: unknown): RealtimeFunctionCall[] {
  if (!response || typeof response !== "object") return [];
  const output = (response as { output?: unknown }).output;
  if (!Array.isArray(output)) return [];
  return output.filter((item): item is RealtimeFunctionCall => Boolean(item && item.type === "function_call"
    && typeof item.call_id === "string" && typeof item.name === "string" && typeof item.arguments === "string"));
}

/** No dynamic tool registry: the voice model can only read memory or search. */
export async function runRealtimeFunctionCall(call: RealtimeFunctionCall, context: {
  token: string; chatId: string; callId: string; turnId: string;
}): Promise<RealtimeToolResult> {
  if (call.name !== "memory_lookup" && call.name !== "web_search") {
    return { content: "This action is not available in voice. Do not claim it was done." };
  }
  try {
    if (call.arguments.length > 2000) throw new Error("oversized arguments");
    const args = JSON.parse(call.arguments);
    if (typeof args.query !== "string" || !args.query.trim() || args.query.length > 500) {
      throw new Error("invalid query");
    }
    return await speechApi.realtimeTool(context.token, {
      chat_id: context.chatId, call_id: context.callId, turn_id: context.turnId,
      name: call.name, query: args.query.trim(),
    });
  } catch {
    return { content: "Lookup failed or timed out. Tell the user what could not be verified; do not guess." };
  }
}
