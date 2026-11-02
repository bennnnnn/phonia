import { createContext, useContext, useMemo, type ReactNode } from "react";

/**
 * What a clarify card needs from the chat around it (docs/clarify.md). Outside a chat
 * (a shared transcript, a test) there is no provider and every card is read-only.
 */
type ClarifyActions = {
  /** Sends a user message through the chat's own send path; false when it refused (offline). */
  send: (text: string) => Promise<boolean>;
  /** A reply is streaming or saving: no card may send now. */
  busy: boolean;
};

/** Where one assistant message stands in the chat. */
type ClarifyMessage = {
  /** The newest assistant reply: only its card may still be answered. */
  latest: boolean;
  /** The user message that came right after this reply, if any: the picks, a skip, or else. */
  nextUserText: string | null;
};

const ClarifyActionsContext = createContext<ClarifyActions | null>(null);
const ClarifyMessageContext = createContext<ClarifyMessage | null>(null);

export function ClarifyActionsProvider({
  send,
  busy,
  children,
}: ClarifyActions & { children: ReactNode }) {
  const value = useMemo(() => ({ send, busy }), [send, busy]);
  return <ClarifyActionsContext.Provider value={value}>{children}</ClarifyActionsContext.Provider>;
}

export function ClarifyMessageScope({
  latest,
  nextUserText,
  children,
}: ClarifyMessage & { children: ReactNode }) {
  const value = useMemo(() => ({ latest, nextUserText }), [latest, nextUserText]);
  return <ClarifyMessageContext.Provider value={value}>{children}</ClarifyMessageContext.Provider>;
}

export function useClarifyActions(): ClarifyActions | null {
  return useContext(ClarifyActionsContext);
}

export function useClarifyMessage(): ClarifyMessage | null {
  return useContext(ClarifyMessageContext);
}
