import { createContext, useContext } from "react";

const ReplyStreamingContext = createContext(false);

/**
 * Whether the reply drawn under it is still streaming. The render rules are
 * the same from a reply's first token to its last, so a reply that finishes
 * keeps every view it drew; the few blocks that differ once it settles (an
 * answer's check, a link's preview card) read this instead.
 */
export const ReplyStreaming = ReplyStreamingContext.Provider;

/** True while the reply this block belongs to is still streaming. */
export function useReplyStreaming(): boolean {
  return useContext(ReplyStreamingContext);
}
