import type { ReactNode } from "react";

import { ClarifyActionsProvider } from "@/components/rich/clarifyContext";
import { EmailDraftPersistProvider } from "@/features/drafts/context/emailDraftPersist";
import type { EmailDraft } from "@/lib/richBlocks";

type Props = {
  /** Saves an edited email card on its message. */
  saveEmailDraft: (messageId: string, draft: EmailDraft) => Promise<boolean>;
  /** Sends a user message through the chat's send path (a clarify card's picks); false when refused. */
  send: (text: string) => Promise<boolean>;
  /** A reply is streaming or saving: cards that send wait. */
  busy: boolean;
  children: ReactNode;
};

/** What the cards inside a reply reach in the chat around them. */
export function ChatReplyProviders({ saveEmailDraft, send, busy, children }: Props) {
  return (
    <EmailDraftPersistProvider save={saveEmailDraft}>
      <ClarifyActionsProvider send={send} busy={busy}>
        {children}
      </ClarifyActionsProvider>
    </EmailDraftPersistProvider>
  );
}
